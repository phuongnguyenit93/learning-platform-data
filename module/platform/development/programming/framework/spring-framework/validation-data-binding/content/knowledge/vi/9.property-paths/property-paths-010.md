# Giới hạn độ sâu, chỉ số và số phần tử từ dữ liệu không tin cậy

Trong Spring Framework, tên tham số form có thể là một **đường dẫn thuộc tính** (*property path*), không chỉ là tên một field đơn lẻ. Ví dụ `customer.name` đi vào object lồng nhau, còn `items[2].quantity` đi vào phần tử thứ ba của danh sách. Nếu người gửi request điều khiển được đường dẫn, ứng dụng phải xem **cả tên tham số lẫn giá trị của nó là dữ liệu không tin cậy**.

Một đường dẫn như `items[999999].quantity` có thể khiến cơ chế binding cố mở rộng collection rất lớn nếu không có giới hạn; một đường dẫn lồng nhiều cấp có thể gây traversal/khởi tạo nhiều object; hàng nghìn tham số có thể làm tăng chi phí parse, chuyển kiểu và validation. Ngoài rủi ro tài nguyên, đường dẫn như `account.admin` còn tạo nguy cơ **mass assignment** nếu target có property writable không dành cho người dùng.

Bài học này phân biệt **độ sâu đường dẫn**, **chỉ số phần tử**, **số phần tử của collection** và **số lượng/thể tích dữ liệu đầu vào**, rồi áp dụng các lớp bảo vệ phù hợp trong `BeanWrapper`, `DataBinder` và Spring MVC. Ví dụ sử dụng Java 17+ và Spring Framework 6.2.x.

## 1. Property path: một chuỗi có thể dẫn qua nhiều object

Spring hỗ trợ các dạng path theo JavaBeans conventions:

| Đường dẫn | Ý nghĩa | Điều cần kiểm soát |
| --- | --- | --- |
| `name` | Property trên target chính | Tên property có được phép bind? |
| `profile.address.city` | Đi qua hai object trung gian | Độ sâu, khả năng khởi tạo object trung gian |
| `items[0].quantity` | Property của phần tử ở chỉ số 0 | Index có nằm trong tập được chấp nhận? |
| `items[150].quantity` | Phần tử ở chỉ số 150 | Có cần auto-grow? Mức cấp phát tối đa? |
| `attributes[channel]` | Giá trị Map tại khóa `channel` | Key có được phép? Map có thể tăng bao nhiêu entry? |
| `sections[0].lines[1].price` | Nhiều tầng collection | Giới hạn đồng thời độ sâu, chỉ số ở từng tầng và tổng số object |

Luồng property binding có thể hình dung như sau:

```text
HTTP/form input:
  "items[1].quantity" -> "3"
                  |
                  v
             WebDataBinder
                  |
         kiểm tra allowedFields
                  |
       phân tích đường dẫn property
                  |
      target.getItems() -> index 1
                  |
     (có thể auto-grow collection)
                  |
    item.setQuantity(convert("3"))
                  |
             BindingResult
```

**Giá trị `"3"` là dữ liệu, nhưng tên `"items[1].quantity"` cũng là dữ liệu.** Việc giới hạn kiểu của `quantity` hoặc dùng `@Min(1)` không đủ để kiểm soát những object nào được tạo và trường nào có thể bị sửa trong khi binding.

Với một request từ UI, các tham số trên form hợp lệ thường được định nghĩa trước. Server có thể đặt quy tắc: chỉ cho phép `customer` cùng `items[0..2].sku`, `items[0..2].quantity`. Khi đó một đường dẫn ngoài phạm vi bị từ chối ngay cả khi target có getter/setter.

## 2. Bốn loại giới hạn cần tách riêng

**Độ sâu** là số tầng object/collection mà một path có thể đi qua. Ví dụ `customer.name` có một bước lồng, còn `order.buyer.address.country.code` có nhiều bước hơn. Độ sâu có ý nghĩa khi hệ thống cho phép đường dẫn tự do hoặc object graph được tạo động.

**Chỉ số** là vị trí cụ thể như `items[2]`. Một index lớn có thể tạo khoảng trống, kích hoạt auto-grow hoặc truy cập ngoài phạm vi; phải kiểm tra tại từng collection, không chỉ tổng độ dài chuỗi.

**Số phần tử** là kích thước collection thực sự mà nghiệp vụ chấp nhận. Giới hạn index là một phần của bài toán nhưng không bao trùm số entry trong Map, số phần tử đã tồn tại, số danh sách con hoặc số item từ JSON.

**Kích thước input** bao gồm số tên tham số, số giá trị lặp của một tên, số byte request và kích thước chuỗi/JSON. Giới hạn tại binder không ngăn servlet container hoặc JSON parser tiêu tốn tài nguyên **trước khi binder được gọi**.

Ví dụ policy cho form đặt hàng giả định:

| Chiều kiểm soát | Ví dụ policy của ứng dụng | Kiểm tra ở đâu? |
| --- | --- | --- |
| Path cho phép | `customer`, `items[0..2].sku`, `items[0..2].quantity` | Allowlist/kiểm tra tên input |
| Độ sâu | Không có path ngoài 2 cấp như `items[i].quantity` | Schema/allowlist hoặc parser path riêng |
| Chỉ số | Chỉ 0, 1, 2 cho `items` | Allowlist từng index + cấu hình auto-grow |
| Số phần tử | Tối đa 3 item | Giới hạn binding + validation contract |
| Số tham số | Tối đa 7 tên tham số của form | HTTP layer và kiểm tra request |
| Kích thước body | Phù hợp kiểu form và tải cho phép | Server/gateway/web container |
| Chuỗi và dữ liệu | `sku` tối đa một độ dài phù hợp | Parsing/validation trước xử lý nghiệp vụ |

Các con số trên **chỉ là ví dụ của một hợp đồng API**, không phải mặc định được Spring áp dụng cho mọi ứng dụng.

## 3. Hiểu đúng auto-grow của DataBinder

`org.springframework.validation.DataBinder` có thể đi qua nested path và tự tạo giá trị khi cần cho property binding. Các API quan trọng:

```java
binder.setAutoGrowNestedPaths(true);
binder.setAutoGrowCollectionLimit(3);
```

Với `DataBinder` chuẩn ở Spring Framework 6.2:

- `setAutoGrowNestedPaths(boolean)` điều khiển việc cố tạo giá trị cho một nested path đang `null` và khả năng auto-grow phần tử collection lúc truy cập index vượt phần tử hiện có. Mặc định thường là `true`.
- `setAutoGrowCollectionLimit(int)` chỉ định mức **tự mở rộng tối đa** cho array/collection khi property binding; mặc định là **256** (hằng `DEFAULT_AUTO_GROW_COLLECTION_LIMIT`).
- Hai cấu hình này áp dụng cho nhánh property binding bằng setter/field access của `DataBinder`. Không coi chúng là chính sách giới hạn chung cho **constructor binding** qua `construct(...)`.
- Auto-grow chỉ thành công khi Spring xác định được kiểu/đường tạo đối tượng con phù hợp. Kiểu trừu tượng, thiếu constructor, collection không thích hợp hoặc path không hợp lệ vẫn có thể gây lỗi.

Ví dụ, `items` đang có 0 phần tử, request gửi `items[2].quantity`. Nếu auto-grow được bật, kiểu phần tử có thể khởi tạo và giới hạn cho phép, Spring có thể mở rộng list để tới index 2. Đổi thành `items[999999].quantity` thì **không nên** được cấp phát một triệu phần tử; `setAutoGrowCollectionLimit(3)` làm giới hạn tự mở rộng trong nhánh đó.

**Giới hạn này không đồng nghĩa “list luôn có không quá 3 phần tử”.** Nếu list đã được cấp 20 phần tử ở nơi khác, auto-grow limit không phải một bước cắt list về 3. Nó cũng không tự giới hạn số entry trong mọi kiểu Map, tổng số object ở nhiều collection hay số tham số HTTP.

Không nên cố xử lý vượt giới hạn bằng cách tăng mặc định từ 256 lên một con số thật lớn. Hãy hỏi nhu cầu nghiệp vụ trước: nếu UI chỉ cho thêm 3 dòng, để auto-grow 3 hoặc thấp hơn là hợp lý; nếu cần import hàng chục nghìn dòng, nên dùng workflow import theo lô và quota riêng thay vì form binding với index tùy ý.

### Giới hạn của BeanWrapper khác gì?

`BeanWrapperImpl` có thể cấu hình `setAutoGrowNestedPaths(...)` và `setAutoGrowCollectionLimit(...)` khi truy cập property trực tiếp. `DataBinder` chuẩn sử dụng cơ chế property access ở dưới và cung cấp các phương thức cấu hình tương ứng.

Tuy nhiên, nếu lập trình viên tự gọi `beanWrapper.getPropertyValue(path)` hoặc `setPropertyValue(path,value)`, không có lớp request security nào tự xuất hiện. Caller vẫn phải xác thực tính hợp lệ của path, quyền thao tác và nguồn input. Nếu chỉ biết tên property ở compile time, gọi getter/setter trực tiếp thường an toàn và dễ kiểm soát hơn một path từ người dùng.

## 4. Ba lớp kiểm soát đường dẫn khi binding dữ liệu HTTP

### Lớp 1: Thiết kế target có phạm vi nhỏ

Dùng **DTO/command object** chỉ chứa dữ liệu mà form được phép nhập. Tránh bind trực tiếp entity có `id`, `ownerId`, `role`, `approved`, `price`, `admin` hay thuộc tính nội bộ. Một property có setter tồn tại không có nghĩa client được quyền thay đổi nó.

Ví dụ, form chỉnh sửa địa chỉ chỉ cần `street`, `city`, `postalCode`. Quyền xác định user có được sửa địa chỉ hay không là trách nhiệm của controller/service, không phải `BeanWrapper`.

Đối với dữ liệu bất biến, **constructor binding** có thể giảm bề mặt property binding. Spring Framework 6.1+ cung cấp `binder.setDeclarativeBinding(true)`: mặc định chỉ dùng các giá trị khai báo cho constructor binding, còn property binding chỉ thực hiện nếu có `allowedFields`. Đây là cơ chế lựa chọn rõ nguồn binding chứ không phải giới hạn byte request, độ sâu tổng quát hay quyền nghiệp vụ.

### Lớp 2: Allowlist property path thực sự được phép

Khi cần property binding, cấu hình:

```java
binder.setAllowedFields(
        "customer",
        "items[0].sku", "items[0].quantity",
        "items[1].sku", "items[1].quantity",
        "items[2].sku", "items[2].quantity"
);
```

Với contract trên:

- `items[1].quantity` hợp lệ nếu target/type cho phép.
- `items[3].quantity` **không nằm trong allowlist**, dù cú pháp path hợp lệ.
- `items[1].price` không hợp lệ dù class có setter `setPrice(...)`.
- `account.admin` không hợp lệ ngay cả khi object graph có property đó.
- `items[0].details.owner.role` không hợp lệ vì đường dẫn sâu hơn contract.

Spring cho phép wildcard trong `allowedFields`, ví dụ `items[*].quantity`. Nó thuận tiện khi index không cố định, nhưng **wildcard tự nó không đặt giới hạn index hay số phần tử**; phải kết hợp mức auto-grow phù hợp và kiểm tra index/key ở biên. Với form nhỏ có số vị trí cố định, cho phép chính xác từng path thường dễ kiểm chứng hơn wildcard.

Có `setDisallowedFields(...)` nhưng cách chặn bằng danh sách cấm dễ bỏ sót field mới hoặc nested field. Với input không tin cậy, ưu tiên **allowedFields** hoặc cấu trúc constructor/DTO chỉ khai báo những đầu vào thực sự cần.

### Lớp 3: Giới hạn auto-grow và kích thước đầu vào

```java
binder.setAutoGrowCollectionLimit(3);
binder.setAutoGrowNestedPaths(true);
```

Chọn collection limit sát nhu cầu thực và kết hợp một giới hạn **số parameter/body ở HTTP layer**. Nếu object graph của form đã được khởi tạo đầy đủ, có thể cân nhắc `setAutoGrowNestedPaths(false)`, rồi kiểm thử kỹ cách bind: tắt auto-grow ngăn khởi tạo node còn null, nhưng không khiến path đi qua node đã có bị từ chối.

Những lớp kiểm soát này bổ sung cho nhau. Allowlist có thể chặn property trước khi phải truy cập collection; auto-grow limit hạn chế cấp phát ngoài ý muốn nếu có đường dẫn tới index chưa tồn tại; HTTP layer giảm chi phí parse trước khi binding.

## 5. Ví dụ Java 17+ chạy được: giới hạn index bằng allowlist và auto-grow

Ví dụ dựng một form có danh sách các dòng hàng. Yêu cầu: tối đa ba vị trí `items[0]`, `items[1]`, `items[2]`, chỉ cho nhập `customer`, `sku` và `quantity`. Ta **cố ý** đặt thêm field `admin` trong form để quan sát một request không mong muốn bị chặn bởi `allowedFields`; trong ứng dụng thật nên bỏ field nhạy cảm khỏi DTO ngay từ thiết kế.

Tạo cấu trúc Maven:

```text
safe-path-binding/
├── pom.xml
└── src/main/java/SafePathBindingDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>safe-path-binding</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/SafePathBindingDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class SafePathBindingDemo {

    public static class Item {
        private String sku;
        private int quantity;

        public Item() {}

        public String getSku() { return sku; }
        public void setSku(String sku) { this.sku = sku; }

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) { this.quantity = quantity; }
    }

    public static class OrderForm {
        private String customer;
        private List<Item> items = new ArrayList<>();
        // Chỉ dùng để chứng minh cơ chế allowlist chặn field nhạy cảm.
        private boolean admin;

        public OrderForm() {}

        public String getCustomer() { return customer; }
        public void setCustomer(String customer) { this.customer = customer; }

        public List<Item> getItems() { return items; }
        public void setItems(List<Item> items) { this.items = items; }

        public boolean isAdmin() { return admin; }
        public void setAdmin(boolean admin) { this.admin = admin; }
    }

    private static DataBinder newBinder(OrderForm target) {
        DataBinder binder = new DataBinder(target, "order");
        binder.setAutoGrowNestedPaths(true);
        binder.setAutoGrowCollectionLimit(3);

        // Chỉ chấp nhận những path thuộc contract của form.
        binder.setAllowedFields(
                "customer",
                "items[0].sku", "items[0].quantity",
                "items[1].sku", "items[1].quantity",
                "items[2].sku", "items[2].quantity"
        );
        binder.setDeclarativeBinding(true);
        return binder;
    }

    public static void main(String[] args) {
        OrderForm normal = new OrderForm();
        DataBinder normalBinder = newBinder(normal);

        MutablePropertyValues validInput = new MutablePropertyValues();
        validInput.add("customer", "An");
        validInput.add("items[1].sku", "BK-2");
        validInput.add("items[1].quantity", "2");
        normalBinder.bind(validInput);

        BindingResult normalResult = normalBinder.getBindingResult();
        System.out.println("customer=" + normal.getCustomer());
        System.out.println("items.size=" + normal.getItems().size());
        System.out.println("item1.sku=" + normal.getItems().get(1).getSku());
        System.out.println("item1.quantity=" +
                normal.getItems().get(1).getQuantity());
        System.out.println("normal.errors=" + normalResult.getErrorCount());

        // Một request khác cố truy cập index rất lớn và field nội bộ.
        OrderForm attempted = new OrderForm();
        DataBinder attemptedBinder = newBinder(attempted);

        MutablePropertyValues untrustedInput = new MutablePropertyValues();
        untrustedInput.add("items[999999].quantity", "20");
        untrustedInput.add("admin", "true");
        attemptedBinder.bind(untrustedInput);

        BindingResult attemptedResult = attemptedBinder.getBindingResult();
        List<String> suppressed =
                Arrays.asList(attemptedResult.getSuppressedFields());

        System.out.println("suppressed.index=" +
                suppressed.contains("items[999999].quantity"));
        System.out.println("suppressed.admin=" +
                suppressed.contains("admin"));
        System.out.println("attempted.items.size=" +
                attempted.getItems().size());
        System.out.println("attempted.admin=" + attempted.isAdmin());
        System.out.println("attempted.errors=" +
                attemptedResult.getErrorCount());
    }
}
```

Chạy từ thư mục `safe-path-binding` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=SafePathBindingDemo
```

Đầu ra mong đợi từ các câu lệnh `System.out.println`:

```text
customer=An
items.size=2
item1.sku=BK-2
item1.quantity=2
normal.errors=0
suppressed.index=true
suppressed.admin=true
attempted.items.size=0
attempted.admin=false
attempted.errors=0
```

**Phân tích kết quả:**

1. `items[1]` hợp lệ và được auto-grow: vì `items` ban đầu rỗng, Spring có thể tạo đủ phần tử để truy cập index 1. `Item` là class công khai có constructor không tham số và setter phù hợp.
2. `"2"` chuyển thành `int 2` trước khi gọi `setQuantity(...)`.
3. `items[999999].quantity` nằm ngoài allowlist nên bị **suppressed**; request không kích hoạt việc mở rộng collection tới index này.
4. `admin=true` cũng bị suppressed dù target của demo có setter `setAdmin(...)`. Trong ứng dụng thật không nên đưa field nhạy cảm vào form DTO.
5. `attemptedResult.getSuppressedFields()` ghi nhận những tên field bị loại bởi cơ chế allowed/disallowed fields. `attemptedResult.getErrorCount()` vẫn là 0: **suppressed field không mặc nhiên trở thành `FieldError`!**

Ví dụ nhấn mạnh hai vấn đề riêng: chặn path không mong muốn và giữ auto-grow limit ở mức nhỏ. Muốn chứng minh mức giới hạn auto-grow khi **không** có allowlist, cần test riêng cho trường hợp index nằm trong pattern được cho phép nhưng vượt giới hạn; không nên dùng cách bind không bảo vệ đó trên dữ liệu thật.

### Không âm thầm chấp nhận các field bị suppressed

Một ứng dụng có thể quyết định trả lỗi client khi request chứa field ngoài contract:

```java
BindingResult result = binder.getBindingResult();

if (result.getSuppressedFields().length > 0) {
    throw new IllegalArgumentException(
            "Request chứa property không được phép cập nhật");
}
if (result.hasErrors()) {
    // Trả lỗi binding/validation có cấu trúc cho người dùng.
}
```

Đây là **đoạn xử lý trong chương trình có binder**, không tự chạy độc lập. Trong Spring MVC, nên chuyển thành phản hồi 4xx với error DTO phù hợp. Không trả nguyên raw path hay giá trị input nhạy cảm ra công khai nếu điều đó làm lộ cấu trúc hoặc dữ liệu nội bộ.

**Quan trọng:** khi gọi `bind(...)`, một số field hợp lệ có thể đã được gán trước khi phát hiện field bị suppressed. Nếu cần ngăn mọi thay đổi của entity trong trường hợp request bị từ chối, **bind vào DTO độc lập** rồi chỉ chuyển sang domain/service sau khi tất cả kiểm tra PASS. `DataBinder` không cung cấp rollback nhiều setter.

## 6. Giới hạn độ sâu không có một nút cấu hình chung

`setAutoGrowCollectionLimit` là giới hạn **auto-growth của collection**, không phải `setMaxPropertyPathDepth`. Trong các API `DataBinder`/`BeanWrapper` thông dụng của Spring Framework 6.2, không nên giả định có một tùy chọn chung tự động chặn mọi đường dẫn vượt N cấp. Framework có thể truy cập nested property đến độ sâu mà object graph và đường truy cập cho phép.

Nếu form chỉ cần `customer` và `items[i].quantity`, allowlist **chính xác toàn bộ path** tự tạo một ranh giới độ sâu hữu ích. Đường dẫn `items[0].detail.owner.profile.secret` sẽ không khớp.

Khi ứng dụng buộc phải cho phép schema động, hãy thiết kế một **bộ phân tích/canonicalizer path được kiểm chứng** để áp dụng đồng thời:

- Danh sách tên property/segment được phép.
- Số segment hoặc số lần đi qua nested object tối đa.
- Mỗi index phải là số nguyên không âm, giới hạn nhỏ hơn độ dài/mức quota phù hợp.
- Số tầng indexed collection và số entry Map tối đa.
- Key Map hợp lệ theo contract, không được tùy ý mở rộng object graph.
- Chiều dài toàn path tối đa và số path khác nhau trong một request.
- Không chấp nhận nhiều cách viết thay thế để vượt policy.

**Đừng viết bộ lọc bảo mật chỉ bằng `path.split("\\.")` rồi đếm dấu chấm.** Path có thể chứa cú pháp `[...]`, key trong Map hoặc ký tự đặc biệt; kiểm tra độ sâu bằng cách đếm dấu chấm sẽ không đếm đúng số tầng indexed và có thể khác cách Spring hiểu path. Đối với form có schema cố định, **allowlist path chính xác** đáng tin cậy hơn một parser tự viết.

Ví dụ chính sách chỉ cho phép các tên:

```text
customer
items[0].sku
items[0].quantity
items[1].sku
items[1].quantity
items[2].sku
items[2].quantity
```

Dù đường dẫn dài hay có bao nhiêu dấu chấm, tên ngoài tập này sẽ bị từ chối. Khi thêm field mới, cần cập nhật contract, test và policy cùng nhau; không dùng wildcard quá rộng như `*` để “giải quyết nhanh”.

## 7. Giới hạn chỉ số và giới hạn số phần tử không phải một việc

Giả sử collection được auto-grow tới index 2; Java list thường có ít nhất 3 vị trí (0, 1, 2). Tuy nhiên, số phần tử thật sự có ý nghĩa nghiệp vụ không nhất thiết bằng kích thước list: một số phần tử có thể là object trống/giá trị mặc định do auto-grow.

Phân biệt:

- **Index lớn nhất được phép:** với ba vị trí, index hợp lệ là 0, 1, 2. Không suy luận rằng index 3 hợp lệ chỉ vì “số lượng tối đa 3”.
- **Số phần tử đã cấp phát:** auto-grow từ list rỗng tới index 2 có thể tạo các phần tử trung gian.
- **Số item nghiệp vụ:** các item có `sku` và `quantity` hợp lệ, có thể yêu cầu không có “lỗ hổng” ở index 0 hoặc 1.
- **Tổng số collection:** ba dòng mỗi nhóm nhưng một request gửi hàng trăm nhóm vẫn có thể tạo nhiều item nếu không giới hạn số nhóm.
- **Map entry count:** Map dùng key, không dùng integer index theo cùng cách; auto-grow limit cho array/list không tự đảm bảo Map chỉ có tối đa 3 entry.

Ví dụ, request chỉ gửi `items[2].quantity=3` không nên mặc nhiên được coi là đơn có đúng một item hợp lệ. Validator cần quy định “không có phần tử trống trước phần tử đã nhập” hoặc phía server tự xây danh sách từ một cấu trúc input đã được giới hạn.

Để ràng buộc **quy tắc nghiệp vụ** trên collection, Jakarta Bean Validation có thể dùng:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import java.util.List;

public class OrderForm {
    @Size(max = 3)
    @Valid
    private List<ItemForm> items;

    // Getter/setter khi dùng property binding.
}
```

Đây là đoạn model minh họa, cần định nghĩa `ItemForm` và provider validation tương ứng. `@Size(max = 3)` kiểm tra list đã có sau khi binding/construct, và `@Valid` cho phép kiểm tra phần tử lồng nhau nếu được kích hoạt. **Nó không ngăn cấp phát xảy ra trước validation**. Vì vậy, `@Size` bổ sung cho giới hạn auto-grow và request, không thay thế chúng.

### Tổng số phần tử quan trọng với nhiều collection lồng nhau

Giả sử body cho phép 50 nhóm và mỗi nhóm 50 item. Dù index từng list nhỏ hơn 50, tổng số phần tử có thể lên tới 2.500. Khi depth tăng, chi phí cấp phát, conversion và validation có thể tăng nhanh theo tổng số node.

Do đó, ngoài max index ở từng list, hãy xác định quota cho **tổng item toàn request**, số nhóm, số child trên mỗi group, số byte body và độ dài string. Nên tính quota trước khi chuyển dữ liệu thành graph lớn hoặc trong lúc parse với cơ chế hỗ trợ, thay vì đợi đến service sau khi object đã được tạo.

## 8. Giới hạn số tham số và kích thước body tại ranh giới HTTP

`DataBinder` được gọi sau khi request đã đi qua một số bước của HTTP stack. Với form encoding như `application/x-www-form-urlencoded`, servlet container có thể parse parameter name/value trước khi Spring controller sử dụng chúng. Khi đó, dù `setAllowedFields` loại bỏ 10.000 path lạ, server vẫn có thể đã bỏ công parse và cấp phát bộ nhớ cho chúng.

Đối với API HTTP, chính sách cần bao gồm:

1. Giới hạn **kích thước request body** (ở reverse proxy, gateway, container hoặc server layer).
2. Giới hạn **số parameter** có thể parse và, khi phù hợp, số giá trị lặp của cùng một tên.
3. Giới hạn kích thước field/path và số entry của object input.
4. Giới hạn thời gian xử lý/timeout và khả năng xử lý đồng thời theo quy mô ứng dụng.
5. Từ chối request quá hạn mức sớm, trả phản hồi thích hợp (thường là 4xx, ví dụ 413 khi vượt giới hạn body).
6. Dùng telemetry/log đã lọc để thấy lỗi vượt quota mà không log nguyên payload nhạy cảm.

Các tên property cấu hình HTTP cụ thể khác nhau giữa **Servlet container** (Tomcat, Jetty, Undertow), **Spring Boot version**, reverse proxy và cấu hình deploy. Cần đọc tài liệu của stack thực tế trước khi đặt giá trị. Tránh giả định mọi hệ thống đều dùng một property Boot duy nhất để giới hạn tất cả kiểu request.

**Đừng quên parameter trùng tên:** một `Map<String,String>` trong demo code mất thông tin nếu một key xuất hiện nhiều lần. HTTP layer có thể nhận nhiều giá trị cho một tên; policy cần cân nhắc số value và cách chọn/ghép giá trị, không chỉ `map.size()`.

## 9. Cấu hình trong Spring MVC bằng @InitBinder

Đoạn sau minh họa cách áp dụng policy trực tiếp cho model attribute `order`:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("order")
void initOrderBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAutoGrowNestedPaths(true);
    binder.setAutoGrowCollectionLimit(3);

    binder.setAllowedFields(
            "customer",
            "items[0].sku", "items[0].quantity",
            "items[1].sku", "items[1].quantity",
            "items[2].sku", "items[2].quantity"
    );
}
```

Đây là **method thuộc một Spring MVC controller hoặc controller advice có phạm vi phù hợp**, không phải chương trình độc lập. `@InitBinder("order")` áp dụng cấu hình cho model attribute có tên `order`. Chữ ký controller có thể có dạng:

```java
@PostMapping("/orders")
String submit(
        @Valid @ModelAttribute("order") OrderForm order,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        // Từ chối request có field không thuộc contract.
        return "bad-request";
    }
    if (errors.hasErrors()) {
        return "order-form";
    }

    // Sau khi input hợp lệ, chuyển DTO vào service nghiệp vụ.
    return "order-success";
}
```

Đây là **đoạn minh họa integration**; ứng dụng cần import Spring MVC, Jakarta Validation, định nghĩa `OrderForm`, template/view và xử lý status HTTP phù hợp. `return "bad-request"` trong ví dụ chỉ là tên view: muốn phản hồi **HTTP 400** thực sự phải đặt status bằng cơ chế MVC phù hợp, ví dụ `ResponseStatusException(HttpStatus.BAD_REQUEST)` hoặc `ResponseEntity` trong controller API.

**`BindingResult` cần đứng sát sau tham số model attribute tương ứng**. Nếu target chứa các field khác không được phép, `allowedFields` chặn chúng trong property binding. Với constructor binding, cân nhắc DTO/constructor chỉ khai báo giá trị cần thiết; `autoGrowCollectionLimit` của `DataBinder` không tự trở thành quota constructor binding. Chỉ xử lý thực sự an toàn khi kiểm tra toàn bộ các tầng của input pipeline.

Khi dùng `@ControllerAdvice` để áp dụng cấu hình chung, cần chú ý mọi form trong phạm vi có thể có contract khác nhau. Không dùng một allowed-fields rộng cho tất cả controller nếu mỗi form cần những path khác nhau.

## 10. Constructor binding và @RequestBody JSON có đường đi khác

Đường dẫn `items[2].quantity` thường liên quan **form/query parameter property binding**, nhưng Spring còn hỗ trợ **constructor binding** vào object immutable và **JSON deserialization** qua HTTP message converter. Các cơ chế này phải được kiểm soát đúng nơi.

| Đường vào | Cơ chế thường dùng | Giới hạn cần kiểm tra |
| --- | --- | --- |
| `@ModelAttribute` mutable DTO | `WebDataBinder` property binding | `allowedFields`, auto-grow, input count/size, DTO |
| `@ModelAttribute` immutable DTO/record | Constructor binding | Constructor schema, số giá trị, indexed args, input/collection quota riêng |
| `@RequestBody` JSON | HTTP message converter (thường Jackson) | Body size, parser/deserializer constraints, DTO shape, collection size, validation |
| Mã ứng dụng tự gọi `BeanWrapper` | Property access trực tiếp | Caller phải kiểm tra path/index/quyền trước lời gọi |

Ví dụ JSON:

```json
{
  "customer": "An",
  "items": [
    {"sku": "BK-2", "quantity": 2}
  ]
}
```

Đối với `@RequestBody`, Jackson thường xây dựng `items` qua JSON array, **không phải** bằng `WebDataBinder.setAutoGrowCollectionLimit(3)` của ví dụ form. Nếu JSON chứa một mảng quá lớn hoặc quá sâu, cần cấu hình giới hạn đọc/deserialize/body cho stack JSON và ràng buộc DTO. Một validator kiểm tra `@Size(max=3)` sau deserialize không ngăn các bước đã tạo một mảng khổng lồ trước đó.

Constructor binding với indexed parameter cũng có khả năng xây dựng danh sách/nested object, nhưng không nên xem auto-grow limit của property binding là quota tự động cho nhánh này. Hãy thiết kế hợp đồng input và test giới hạn tương ứng với cách dữ liệu thật đi vào ứng dụng.

## 11. Phân biệt rejected, suppressed và lỗi thực thi

Khi kiểm tra một request không hợp lệ, cần phân biệt ba nhóm:

| Hiện tượng | Ví dụ | Nơi quan sát |
| --- | --- | --- |
| **Suppressed field** | `admin=true` hoặc `items[999999].quantity=2` bị allowlist loại | `BindingResult.getSuppressedFields()` |
| **Binding/conversion error** | `items[0].quantity=abc` không chuyển thành `int` | `BindingResult.getFieldErrors()`, thường mã `typeMismatch` |
| **Rule validation error** | `quantity=0` không đạt `@Min(1)` hoặc custom validator | `BindingResult` sau khi validation được kích hoạt |

Trong một số trường hợp path/collection vượt khả năng truy cập, exception liên quan tới `InvalidPropertyException`, `NullValueInNestedPathException` hoặc lỗi truy cập khác có thể xuất hiện tùy đường chạy. Không xây policy bảo vệ bằng giả định “mọi index lớn chắc chắn biến thành một FieldError để controller xử lý”. **Từ chối trước bằng schema/allowlist và giới hạn HTTP**, rồi xử lý các loại exception phù hợp.

**`getSuppressedFields()` không phải phương thức `hasErrors()`.** Một request có các field bị suppressed vẫn có thể báo `hasErrors() == false`. Nếu chính sách yêu cầu phát hiện input bất thường, hãy kiểm tra suppressed fields riêng.

**Thông báo trả người dùng không cần chứa raw path nhạy cảm.** Có thể dùng code ổn định như `INVALID_FIELD`, `INPUT_TOO_LARGE` hoặc `INVALID_INDEX`; log an toàn ở phía server chỉ lưu metadata cần thiết cho phân tích.

## 12. Những giới hạn mà cấu hình binder không thay thế

### 12.1. @Valid và @Size chạy sau khi dữ liệu đã được bind

`@Valid`, `@Validated`, `@Size`, `@Min` có vai trò xác định dữ liệu **hợp lệ về nghiệp vụ**. Nhưng đối với đường property binding, conversion/auto-grow thường xảy ra trước khi validation được chạy. Kiểm tra `list.size() <= 3` sau đó vẫn có giá trị cho contract, nhưng không phải cơ chế ngăn cấp phát ngay từ đầu.

### 12.2. setAutoGrowNestedPaths(false) không phải max depth

Tắt auto-grow ngăn Spring cố tạo một nested object khi path tới object đang `null`. Nó **không** ngăn truy cập một graph lồng sâu nếu mọi object trung gian đã được khởi tạo và property writable.

### 12.3. setAutoGrowCollectionLimit không phải max collection size

Đây là giới hạn **tự mở rộng collection trong property binding**, không phải quota cuối cùng cho list đã tồn tại, Map, JSON, số param HTTP hay tổng phần tử trong graph lồng nhau.

### 12.4. allowedFields không bảo vệ bước HTTP parsing

Một path ngoài allowlist có thể bị loại khi binding nhưng đã tiêu tốn tài nguyên để nhận và parse request. Phải giới hạn số parameter và kích thước request ở biên phù hợp.

### 12.5. BindingResult không thay kiểm soát quyền

Một path hợp lệ và giá trị hợp lệ vẫn có thể bị người gọi sử dụng trái phép theo nghiệp vụ. Kiểm tra authorization thuộc lớp service/security và có thể phụ thuộc tài nguyên/người dùng hiện tại.

### 12.6. Wildcard rộng có thể phá contract

`items[*].quantity` cho phép tên field chứa nhiều index khác nhau ở tầng matching. Nếu muốn tối đa 3 vị trí, phải bổ sung index boundary rõ, chứ không dựa vào wildcard để tự hạn chế. Một wildcard kiểu `*` có thể vô tình cho phép cả field ngoài ý định.

## 13. Bộ kiểm thử ranh giới nên có

Với form có tối đa ba vị trí `items`, hãy kiểm tra cả trường hợp hợp lệ và trường hợp bị từ chối:

| Request | Kỳ vọng ở form binding có allowlist ở phần 5 |
| --- | --- |
| `items[0].sku=BK-1` | Được phép về path; còn cần validation dữ liệu |
| `items[2].quantity=3` | Được phép; trong mức ba vị trí |
| `items[3].quantity=3` | Bị suppressed vì ngoài allowlist |
| `items[999999].quantity=3` | Bị suppressed; không auto-grow đến index này |
| `items[-1].quantity=3` | Không thuộc allowlist; bị suppressed |
| `items[0].secret=true` | Bị suppressed vì property không được khai báo |
| `customer=An` | Được phép |
| `admin=true` | Bị suppressed dù demo có setter |
| `items[1].quantity=abc` | Path được phép, nhưng chuyển kiểu có thể tạo binding error |
| `items[0].details.owner.role=admin` | Bị suppressed vì path sâu hơn contract |
| Hàng nghìn field bất kỳ | Phải bị ngăn ở HTTP limit/kiểm tra request; không chỉ trông chờ binder |
| JSON array hàng nghìn phần tử | Cần body/parser constraint riêng; cấu hình binder form không đủ |

Khi thử nghiệm những giá trị index lớn hoặc path sâu, chỉ dùng test có giới hạn tài nguyên trong môi trường kiểm soát; tránh tạo request đủ lớn gây ảnh hưởng hệ thống dùng chung. Unit test có thể xác minh policy qua danh sách path giả lập mà không phải thực sự cấp phát collection khổng lồ.

Đặc biệt, test phải kiểm tra cả **giá trị target sau bind** lẫn `BindingResult`. Chỉ assert `hasErrors()==false` là chưa đủ: request có field bị suppressed có thể vẫn trả false. Với các request mà policy muốn từ chối, assert `getSuppressedFields()` có tên đã bị loại và controller không gọi service xử lý nghiệp vụ.

## 14. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Cho phép path bất kỳ từ request | Mass assignment, graph không kiểm soát | DTO nhỏ + allowedFields chính xác |
| Chỉ dùng `setAutoGrowCollectionLimit(3)` | Không hạn chế Map, số path, độ sâu, list đã có | Bổ sung quota theo từng chiều |
| Nâng limit lên hàng triệu để “hỗ trợ nhiều dòng” | Nguy cơ cấp phát bất thường | Chọn workflow import phân lô, quota rõ |
| Chỉ dùng `@Size(max=3)` | Kiểm tra sau khi object đã được tạo | Giới hạn tại HTTP và trong quá trình binding |
| Chỉ đếm dấu chấm của path | Bỏ qua các tầng `[index]` và Map key | Allowlist hoặc parser path có contract xác định |
| Dùng `items[*].*` quá rộng | Cho phép các field ngoài ý định và nhiều index | Whitelist path cụ thể hoặc parse index chặt |
| Coi suppressed fields là validation errors | Không phát hiện request bất thường | Đọc `getSuppressedFields()` riêng |
| Bind trực tiếp vào JPA entity | Có thể cập nhật field nội bộ trước khi validate | Bind vào DTO, sau PASS mới áp dụng ở service |
| Dựa vào auto-grow limit cho JSON | Cấu hình không áp dụng đường Jackson deserialize | Dùng JSON body/parser quota và validation |
| Không giới hạn số parameter ở HTTP layer | Container đã parse dữ liệu lớn trước binder | Cấu hình container/gateway phù hợp |
| Chia sẻ target mutable giữa request | Lẫn trạng thái, nguy cơ lỗi đồng thời | Tạo target/binder theo request, không cache form state |
| Trả nguyên BindingResult/log giá trị nhạy cảm | Rò rỉ input và cấu trúc nội bộ | Chuẩn hóa mã lỗi, giới hạn logging |

## 15. Checklist cấu hình một form an toàn

1. **Xác định contract:** những field nào được phép, kiểu gì, path sâu tối đa bao nhiêu, số dòng/entry bao nhiêu, kích thước request tối đa bao nhiêu.
2. **Thiết kế DTO:** loại khỏi target mọi thuộc tính không thuộc form; chọn constructor binding khi phù hợp.
3. **Đăng ký allowlist** nếu dùng property binding; với index cố định, liệt kê chính xác các path.
4. **Giới hạn auto-grow:** chọn `setAutoGrowCollectionLimit(n)` dựa trên số vị trí cần, không để vô hạn.
5. **Chọn chính sách nested:** chỉ bật auto-grow nested paths khi thực sự muốn tạo object trung gian.
6. **Giới hạn ở HTTP layer:** body bytes, parameter count và các quota khác theo stack deploy.
7. **Dùng validation cho rule nghiệp vụ:** `@Size`, `@Min`, custom validator, kiểm tra tính liên tục của list và tổng item.
8. **Đọc cả suppressed fields và errors:** phân biệt field ngoài contract với lỗi chuyển kiểu và lỗi validation.
9. **Chỉ gọi service sau PASS:** chuyển DTO sang domain với authorization/transaction phù hợp.
10. **Kiểm thử biên:** index 0, index cuối hợp lệ, index ngay sau giới hạn, index rất lớn, path quá sâu, parameter dư, JSON array quá lớn.
11. **Theo dõi tài nguyên:** request bị từ chối, thời gian parse/bind, exception và rate-limit ở mức phù hợp.

## 16. Tự kiểm tra kiến thức

**1. `setAutoGrowCollectionLimit(3)` có giới hạn mọi list trong object luôn có tối đa ba phần tử không?**  
Không. Nó giới hạn tự mở rộng array/collection trong property binding. List có sẵn, Map, JSON hoặc tổng các list cần quota khác.

**2. `items[999999].quantity` xuất hiện trong form có allowlist chỉ gồm `items[0..2]`. Điều gì xảy ra?**  
Path không nằm trong allowed fields và bị suppressed trước khi thao tác property. Nếu app muốn từ chối request bất thường, phải kiểm tra `BindingResult.getSuppressedFields()`.

**3. `@Size(max=3)` có chặn việc tạo list lớn ngay từ HTTP parsing không?**  
Không. Đây là validation về kích thước dữ liệu sau binding/deserialization. Cần limit trước và trong quá trình xử lý input.

**4. Tắt `setAutoGrowNestedPaths(false)` có nghĩa mọi path sâu bị từ chối không?**  
Không. Nó không tự tạo node null; path qua các object đã hiện hữu vẫn có thể được truy cập.

**5. `allowedFields("items[*].quantity")` đã đủ ngăn mọi index lớn chưa?**  
Chưa. Wildcard matching không phải giới hạn số nguyên index. Cần quota index/auto-grow/HTTP và kiểm thử.

**6. Vì sao cần giới hạn request body/số parameter ngoài `DataBinder`?**  
Vì parsing có thể diễn ra trước khi binder lọc field. Binder không hoàn tác chi phí đã xảy ra ở HTTP stack.

**7. Một request chứa field bị suppressed nhưng `hasErrors()==false` có nên được xem là hợp lệ?**  
Tùy policy, nhưng với API yêu cầu strict schema, phải từ chối theo `getSuppressedFields()`. Suppressed field không mặc nhiên được đếm là lỗi validation.

**8. Giới hạn auto-grow form có áp dụng cho `@RequestBody` JSON của Jackson không?**  
Không thể giả định. JSON đi qua message converter khác; cần ràng buộc cấu trúc, kích thước và parser/DTO riêng.

**Ghi nhớ:** bảo vệ property binding cần kiểm soát **path nào được phép**, **độ sâu và index nào được phép**, **số node có thể được tạo**, và **lượng input nhận từ HTTP**. `setAutoGrowCollectionLimit` là một lớp bảo vệ tài nguyên quan trọng, nhưng contract DTO, allowlist, giới hạn request và validation mới tạo thành một quy trình hoàn chỉnh.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Data Binding và BeanWrapper](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — @InitBinder và thiết kế model an toàn](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Spring MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
