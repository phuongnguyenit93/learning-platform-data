# autoGrowCollectionLimit và phạm vi áp dụng theo kiểu truy cập trong Spring DataBinder

## 1. Vấn đề: một chỉ số từ request có thể làm collection tự phình ra

Spring hỗ trợ **đường dẫn thuộc tính** (property path) như `customer.name`, `lines[0].sku` và `lines[3].quantity`. Khi một `DataBinder` gắn dữ liệu vào JavaBean, nó có thể tự tạo object lồng nhau hoặc mở rộng list/array để tiếp cận phần tử được nhắc tới. Tính năng này tiện khi biểu mẫu gửi nhiều dòng đặt hàng; nó cũng có thể làm ứng dụng cấp phát nhiều đối tượng ngoài dự định nếu người gửi kiểm soát chỉ số.

Ví dụ form gửi:

~~~text
lines[2].sku=SKU-003
~~~

Nếu `lines` ban đầu chưa tồn tại và cấu hình cho phép tự mở rộng, Spring có thể tạo list, làm list đủ độ dài để có vị trí thứ ba (chỉ số 2), tạo phần tử lồng nhau tương ứng rồi gắn `sku`. Chỉ một field đầu vào đã có thể khiến nhiều phần tử hoặc object được cấp phát.

Một đầu vào như `lines[1000000].sku=X` lại là rủi ro tài nguyên nếu ứng dụng cố tạo quá nhiều phần tử. `DataBinder.setAutoGrowCollectionLimit(int)` là một cơ chế kiểm soát quá trình **tự mở rộng collection do đường dẫn chỉ số** trong các chế độ mà phiên bản Spring hỗ trợ.

**Điều phải phân biệt ngay từ đầu:** `setAutoGrowCollectionLimit` khác `setAutoGrowNestedPaths`. Một cấu hình đặt **ngưỡng tự mở rộng collection**; cấu hình còn lại bật/tắt **việc tự tạo đường dẫn lồng nhau khi gặp null và mở rộng phần tử qua indexed path**. Cả hai khác với giới hạn độ lớn HTTP request hoặc validation `@Size`.

## 2. Hai cấu hình cốt lõi và giá trị mặc định

| Cấu hình của `DataBinder` | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `setAutoGrowNestedPaths(boolean)` | `true` trên `DataBinder` tiêu chuẩn | Khi cho phép, cố tạo đối tượng ở đoạn null của đường dẫn; đồng thời cho phép tự mở rộng phần tử collection khi đi qua chỉ số ngoài kích thước hiện tại |
| `setAutoGrowCollectionLimit(int)` | `256` | Ngưỡng chỉ số dành cho **tự mở rộng array/collection** trong chế độ được hỗ trợ; không có nghĩa mọi collection của ứng dụng đều bị giới hạn tối đa 256 phần tử |
| `getAutoGrowCollectionLimit()` | Trả về giá trị đã cấu hình | Dùng kiểm tra cấu hình binder, nhưng **không tự chứng minh** rằng cùng một giới hạn được thực thi cho mọi kiểu truy cập |

Ví dụ:

~~~java
DataBinder binder = new DataBinder(orderForm, "orderForm");
binder.setAutoGrowNestedPaths(true);
binder.setAutoGrowCollectionLimit(32);
~~~

Đây là đoạn **minh họa** với `orderForm` là một object đã có. Theo cách dùng chuẩn, hãy cấu hình các thuộc tính này **trước khi tạo/khởi tạo BindingResult hoặc bắt đầu bind**, để accessor thực sự được thiết lập với cấu hình mong muốn.

### 2.1. Chỉ số được tính từ 0 và điều kiện mở rộng

Giả sử `List<Line> lines` ban đầu rỗng và giới hạn là **4**:

| Đường dẫn nhập | Kết quả dự kiến khi bean-property binding có auto-grow |
| --- | --- |
| `lines[0].sku` | Có thể mở rộng đến 1 phần tử |
| `lines[2].sku` | Có thể mở rộng đến 3 phần tử |
| `lines[3].sku` | Có thể mở rộng đến 4 phần tử |
| `lines[4].sku` | Không được **tự mở rộng** từ list rỗng tới chỉ số 4 vì `4` không nhỏ hơn giới hạn `4` |

Vì chỉ số bắt đầu từ 0, ngưỡng 4 tương ứng với **chỉ số lớn nhất có thể tự mở rộng là 3**. Phát biểu chính xác là: trong logic auto-growth tương ứng, chỉ mở rộng khi **`index < autoGrowCollectionLimit`** và các điều kiện khác đều cho phép.

Không suy ra rằng `lines[4]` luôn bị từ chối: nếu list đã **có sẵn** ít nhất 5 phần tử, việc gắn vào một chỉ số hiện hữu không đòi hỏi auto-grow. Vì vậy `autoGrowCollectionLimit` **không phải** giới hạn số lượng phần tử tuyệt đối cho mọi list và không thay thế quy tắc giới hạn số dòng đơn hàng.

### 2.2. Điều gì xảy ra khi vượt giới hạn?

Đối với `List` tiêu chuẩn hoặc array cần tự mở rộng, Spring sẽ không cấp phát thêm phần tử vượt ngưỡng cấu hình trong luồng áp dụng ngưỡng đó. Việc truy cập chỉ số chưa tồn tại có thể thất bại với ngoại lệ thuộc nhóm lỗi đường dẫn/thuộc tính (chẳng hạn `InvalidPropertyException`), thay vì luôn trở thành một `FieldError` có thể đọc bằng `BindingResult.hasErrors()`.

Không nên viết mã dựa vào giả định “chỉ số quá giới hạn chắc chắn trả HTTP 400 và luôn ghi một `FieldError`”. Cách xử lý phụ thuộc vị trí lỗi, loại container, kiểu binding, phiên bản Spring và cấu hình MVC/exception handler. Nếu đây là dữ liệu từ web, hãy **kiểm soát cấu trúc request đầu vào** và thiết kế phản hồi lỗi có chủ đích.

## 3. Quan hệ với property path và autoGrowNestedPaths

Một đường dẫn có thể chứa nhiều đoạn:

~~~text
order.customer.address.city
order.lines[2].sku
order.lines[2].options[1].label
~~~

Muốn gắn `order.lines[2].sku`, binder cần lần lượt đi qua `order`, `lines`, phần tử thứ ba, rồi `sku`. Với `setAutoGrowNestedPaths(true)`, accessor có thể cố tạo các đoạn chưa có giá trị, tùy khả năng xác định kiểu và khởi tạo đối tượng.

Để làm được điều đó, mô hình thường cần:

- Một target object thực sự tồn tại (trừ trường hợp đang thực hiện constructor binding theo cơ chế riêng).
- Kiểu thuộc tính lồng nhau được khai báo rõ, ví dụ `List<OrderLine>` thay vì `List` raw type không xác định element type.
- Kiểu phần tử có cách khởi tạo phù hợp (ví dụ constructor không tham số có thể sử dụng); không phải abstract/interface tùy ý mà Spring đều biết cách tạo.
- Đường dẫn truy cập hợp lệ trong chế độ **bean-property** hoặc **direct-field** đã chọn.
- Collection phù hợp để mở rộng; list bất biến (`List.of(...)`), list cố định kích thước hoặc phần tử không khởi tạo được có thể gây lỗi.

Khi đặt `setAutoGrowNestedPaths(false)`, truy cập các đoạn `null` hoặc indexed path vượt kích thước hiện tại thường không được tự tạo/mở rộng. **Không** diễn giải `setAutoGrowCollectionLimit(256)` thành hành vi auto-grow luôn được bật: một ngưỡng khác 0 không tự bật lại cấu hình nested path bị tắt.

### 3.1. Nested-object growth và collection growth là hai thao tác

Giả sử:

~~~java
public class OrderForm {
    private Address shippingAddress;
    private List<OrderLine> lines;
    // getter/setter phù hợp
}
~~~

- `shippingAddress.city=Hanoi` có thể khiến `shippingAddress` được tạo, nhưng đây là **khởi tạo object lồng nhau**, không phải mở rộng collection theo chỉ số.
- `lines[3].sku=S4` có thể khiến `lines` được tạo, list tăng đủ chỗ và phần tử thứ tư xuất hiện.
- `lines[3].options[2].label=Gift` có thể tạo nhiều tầng và nhiều phần tử; giới hạn của mỗi thao tác auto-grow **không tự biến thành giới hạn tổng số object hoặc độ sâu đường dẫn**.

Nói cách khác, `autoGrowCollectionLimit` kiểm soát **một dạng mở rộng collection**, không phải bộ giới hạn mọi chi phí xử lý nested property path.

## 4. Phạm vi áp dụng theo kiểu truy cập: bean property và direct field

Đây là điểm quan trọng nhất của bài. Cùng một `DataBinder` có hai đường truy cập:

~~~java
binder.initBeanPropertyAccess(); // Mặc định: JavaBean getter/setter.
binder.initDirectFieldAccess();  // Thay thế: thao tác trực tiếp lên field.
~~~

Hai lệnh trên là **hai lựa chọn thay thế**, không phải hai lệnh cần chạy liên tiếp trong cùng một lần bind.

### 4.1. Bean-property access (mặc định)

- Dùng `BeanWrapper` và quy ước getter/setter để đọc/ghi thuộc tính.
- `setAutoGrowNestedPaths(true)` có thể mở rộng các đường dẫn thích hợp.
- `setAutoGrowCollectionLimit(n)` giới hạn phạm vi **auto-grow array/list** trong luồng property binding này.
- Đây là chế độ phù hợp nhất để học và kiểm chứng giới hạn trên mô hình form JavaBean.

~~~java
DataBinder binder = new DataBinder(new OrderForm(), "orderForm");
binder.setAutoGrowCollectionLimit(4);
binder.bind(propertyValues);
~~~

Đây là đoạn minh họa cần `OrderForm` và `propertyValues` đã tồn tại. Ví dụ đầy đủ ở mục 6 cung cấp những phần đó.

### 4.2. Direct-field access

- `initDirectFieldAccess()` sử dụng `DirectFieldAccessor`, đọc/ghi field trực tiếp thay vì thông qua getter/setter JavaBean.
- Cơ chế auto-grow nested path đã được hỗ trợ trong direct-field access ở nhiều phiên bản Spring.
- **Tuy nhiên, khả năng auto-grow không đồng nghĩa giới hạn chỉ số được triển khai giống bean-property access ở mọi phiên bản.**

Theo mã nguồn và ghi chú phiên bản của Spring:

| Dòng phiên bản | `setAutoGrowNestedPaths` với direct field | `setAutoGrowCollectionLimit` với direct field |
| --- | --- | --- |
| Spring 6.2.x và Spring 7.0.x | Có hỗ trợ auto-grow cho đường dẫn phù hợp | **Không nên coi ngưỡng đặt trên DataBinder là giới hạn hữu hiệu cho direct-field auto-growth**; implementation dòng này chủ yếu áp dụng giới hạn trong bean-property binding |
| Spring 7.1 trở lên | Có hỗ trợ | Spring mở rộng khả năng áp dụng `autoGrowCollectionLimit` cho **field injection/direct-field binding**; cần kiểm tra đúng API/phiên bản thực tế khi triển khai |

Lưu ý về tài liệu: một số Javadoc cũ mô tả ngắn gọn “setter/field injection”, dễ khiến người đọc nghĩ hai cơ chế giống nhau. Ghi chú cải chính trong mã nguồn Spring 7.1 nêu rõ phạm vi theo **setter injection**, và **từ 7.1 mới mở rộng sang field injection**. Vì vậy khi dùng Spring 6.2/7.0, hãy xét hành vi của implementation và viết regression test cho cấu hình thực tế, thay vì chỉ xem giá trị trả về từ `getAutoGrowCollectionLimit()`.

**Hệ quả thiết kế:** không chuyển sang `initDirectFieldAccess()` để né getter/setter trong một đối tượng nhận dữ liệu không tin cậy; cách này có thể bỏ qua các bất biến được bảo vệ qua setter và làm yếu những giả định về giới hạn auto-grow. Direct field access chỉ nên dùng khi hiểu rõ object model và luồng nhập liệu đáng tin cậy.

### 4.3. Phân biệt access mode với cơ chế binding

**Bean-property access** và **direct-field access** là hai cách ghi thuộc tính trong `bind(PropertyValues)`. Còn **constructor binding** (`construct(ValueResolver)`) là một cơ chế khác dùng để tạo object từ constructor arguments, bao gồm các tham số collection.

`setAutoGrowCollectionLimit` **không áp dụng** cho constructor binding qua `DataBinder.construct(...)` trong các phiên bản được đề cập. Constructor binding cần giới hạn đầu vào theo cách riêng: số lượng phần tử, kích thước request, số cấp lồng nhau, contract của DTO và validation có chủ đích. Đừng hiểu “đã đặt limit=32” là mọi trường hợp `construct()` chỉ được phép có tối đa 32 phần tử.

### 4.4. Map keys và những cấu trúc không thuộc phạm vi giới hạn

`items[2]` là **chỉ số số học** trên list/array. `labels[priority]` có thể là **key của Map**. Chúng có hình thức đường dẫn gần giống nhau nhưng khác semantics.

~~~text
items[2].name
labels[priority]
translations[vi].title
~~~

`autoGrowCollectionLimit` không phải giới hạn số key của `Map`, cũng không giới hạn số phần tử của JSON array được Jackson tự deserialize. Một ứng dụng nhận Map hoặc request body JSON lớn phải tự áp đặt quota phù hợp. Với collection custom, cách `get(index)` hoặc `add(...)` hoạt động cũng ảnh hưởng tới khả năng cấp phát tài nguyên.

## 5. Sự khác biệt có thể kiểm chứng qua bảng trường hợp

Giả sử các đối tượng mới có `List<OrderLine> lines` ban đầu null và áp dụng Spring 7.0.9:

| Tình huống | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Property binding, index 2 | `autoGrowNestedPaths=true`, limit 4 | Có thể tạo list 3 phần tử; gắn `lines[2].sku` |
| Property binding, index 2 | limit 2 | Không được auto-grow để chạm index 2; thao tác không được chấp nhận như một binding hợp lệ |
| Property binding, index đã tồn tại | List có 10 phần tử, limit 2 | Việc **ghi vào** phần tử hiện có không nhất thiết bị chặn do limit thấp |
| Property binding, nested null | `autoGrowNestedPaths=false` | Không tự khởi tạo đoạn null để đi tiếp |
| Direct-field binding | Gọi `initDirectFieldAccess()` | Đọc/ghi field trực tiếp; **không giả định** cùng một limit được thực thi ở Spring 7.0 |
| Constructor binding | Gọi `construct(...)` | `setAutoGrowCollectionLimit` không kiểm soát kích thước dữ liệu constructor |
| `@RequestBody` JSON | Jackson deserialize JSON | Không chịu giới hạn này theo cơ chế form/property binding của DataBinder |

**Không nên tạo request có chỉ số cực lớn để “test” giới hạn trên một dịch vụ thật.** Hãy dùng các ngưỡng nhỏ và dữ liệu tổng hợp trong unit test cô lập để quan sát hành vi mà không gây cấp phát ngoài ý muốn.

## 6. Ví dụ Java 17+ đầy đủ: so sánh property access và direct-field access

Ví dụ chạy **không cần servlet hay Spring Boot server**. Nó minh họa ba điểm:

1. `BeanWrapper` trong `DataBinder` tự mở rộng list cho `lines[2].sku` khi limit là 4.
2. Khi limit là 2, việc cố gắn vào chỉ số 2 không đạt kết quả ghi hợp lệ. Vì cách thông báo lỗi có thể tùy hoàn cảnh, ví dụ kiểm tra **trạng thái thực tế** và bắt ngoại lệ trong nhánh quá giới hạn.
3. `initDirectFieldAccess()` vẫn có thể gắn phần tử ở chỉ số nhỏ, không thông qua getter/setter của object gốc. Không sử dụng thao tác vượt limit trong direct-field mode vì semantics giới hạn thay đổi theo phiên bản.

Ví dụ dùng `spring-context 7.0.9` là nhánh có bản vá công khai cho CVE liên quan đến tự mở rộng list (mục 8). Khi áp dụng trong dự án Spring Boot, ưu tiên BOM/Dependency Management của dự án thay vì ép phiên bản Spring một cách tùy tiện.

Cấu trúc:

~~~text
collection-growth-demo/
├── pom.xml
└── src/main/java/CollectionGrowthDemo.java
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>collection-growth-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. src/main/java/CollectionGrowthDemo.java

~~~java
import java.util.List;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

public class CollectionGrowthDemo {

    public static class OrderLine {
        private String sku;

        public OrderLine() {
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }
    }

    public static class BeanOrder {
        private List<OrderLine> lines;

        public List<OrderLine> getLines() {
            return lines;
        }

        public void setLines(List<OrderLine> lines) {
            this.lines = lines;
        }
    }

    public static class FieldOrder {
        // Không có getter/setter JavaBean cho "lines".
        private List<OrderLine> lines;

        public List<OrderLine> snapshot() {
            return lines;
        }
    }

    private static MutablePropertyValues input(
            String path, String value) {

        MutablePropertyValues values = new MutablePropertyValues();
        values.add(path, value);
        return values;
    }

    public static void main(String[] args) {
        DataBinder defaults = new DataBinder(new BeanOrder());
        System.out.println("default.limit="
                + defaults.getAutoGrowCollectionLimit());

        // Case 1: index 2 < limit 4, có thể tạo 3 phần tử.
        BeanOrder beanOrder = new BeanOrder();
        DataBinder beanBinder = new DataBinder(beanOrder, "beanOrder");
        beanBinder.setAutoGrowNestedPaths(true);
        beanBinder.setAutoGrowCollectionLimit(4);
        beanBinder.bind(input("lines[2].sku", "SKU-003"));

        System.out.println("bean.size=" + beanOrder.getLines().size());
        System.out.println("bean.third="
                + beanOrder.getLines().get(2).getSku());
        System.out.println("bean.errors="
                + beanBinder.getBindingResult().hasErrors());

        // Case 2: index 2 không nhỏ hơn limit 2.
        BeanOrder limitedOrder = new BeanOrder();
        DataBinder limited = new DataBinder(limitedOrder, "limitedOrder");
        limited.setAutoGrowCollectionLimit(2);

        boolean overLimitWritten = false;
        try {
            limited.bind(input("lines[2].sku", "SHOULD-NOT-WRITE"));
            List<OrderLine> list = limitedOrder.getLines();
            overLimitWritten = list != null
                    && list.size() > 2
                    && list.get(2) != null
                    && "SHOULD-NOT-WRITE".equals(list.get(2).getSku())
                    && !limited.getBindingResult().hasErrors();
        } catch (RuntimeException ex) {
            // Vượt giới hạn có thể làm hỏng việc truy cập property path.
            // Không dựa vào một lớp exception cố định cho mọi version.
        }
        System.out.println("bean.overLimitWritten=" + overLimitWritten);

        // Case 3: truy cập trực tiếp field với chỉ số nhỏ.
        FieldOrder fieldOrder = new FieldOrder();
        DataBinder fieldBinder = new DataBinder(fieldOrder, "fieldOrder");
        fieldBinder.initDirectFieldAccess();
        fieldBinder.setAutoGrowNestedPaths(true);
        fieldBinder.setAutoGrowCollectionLimit(2);
        fieldBinder.bind(input("lines[1].sku", "FIELD-002"));

        System.out.println("field.size=" + fieldOrder.snapshot().size());
        System.out.println("field.second="
                + fieldOrder.snapshot().get(1).getSku());
        System.out.println("field.errors="
                + fieldBinder.getBindingResult().hasErrors());
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=CollectionGrowthDemo
~~~

Output mong đợi từ các lệnh `System.out.println(...)` (bỏ qua log riêng của Maven):

~~~text
default.limit=256
bean.size=3
bean.third=SKU-003
bean.errors=false
bean.overLimitWritten=false
field.size=2
field.second=FIELD-002
field.errors=false
~~~

Giải thích:

- `BeanOrder` có getter/setter cho `lines`, nên mode mặc định là bean-property access. Từ một list null, Spring có thể tạo `ArrayList<OrderLine>`, bổ sung vị trí cần có và tạo phần tử `OrderLine` để gắn `sku`.
- Với limit 4, chỉ số 2 đủ nhỏ: `lines` có độ dài 3 và giá trị ở vị trí thứ ba bằng `SKU-003`.
- Với limit 2, chỉ số 2 không còn thuộc phạm vi **auto-grow** cho list rỗng; nhánh `try/catch` cho thấy không có một lần ghi hợp lệ vào vị trí đó. Ví dụ không tuyên bố “luôn ném cùng exception” hoặc “luôn chỉ có BindingResult error”.
- `FieldOrder` **không có getter/setter** cho `lines`, nhưng `initDirectFieldAccess()` cho phép binder thao tác với field. Vì ví dụ dùng chỉ số 1, nó chỉ chứng minh **khả năng binding ở direct-field mode**; không dùng kết quả này để kết luận direct-field limit luôn được áp dụng như bean-property mode.
- `OrderLine` có constructor không tham số có thể sử dụng; generic `List<OrderLine>` giúp Spring biết loại phần tử cần tạo.

**Giới hạn xác minh:** chương trình và stdout đã được rà soát theo API, nhưng cần chạy Maven trong môi trường có dependencies phù hợp để có bằng chứng thực thi của chính môi trường đó. Ví dụ cố ý tránh cấp phát collection lớn.

## 7. Áp dụng vào Spring MVC và WebDataBinder

Khi controller xử lý `@ModelAttribute`, có thể thiết lập ngưỡng cho binder theo tên form qua `@InitBinder`. Đoạn dưới là **mã minh họa trong controller hiện có**, không phải ứng dụng Spring MVC độc lập:

~~~java
@InitBinder("orderForm")
void configureOrderForm(WebDataBinder binder) {
    binder.setAutoGrowNestedPaths(true);
    binder.setAutoGrowCollectionLimit(32);
    binder.setAllowedFields(
            "customerName",
            "lines[*].sku",
            "lines[*].quantity"
    );
}
~~~

Từ đó:

- Ngưỡng 32 định hướng giới hạn **tự mở rộng** list/array trong luồng property binding tương ứng, không phải giới hạn tổng số request fields, số nested objects, số bytes hoặc số item đã tồn tại.
- `setAllowedFields(...)` là whitelist các đường dẫn được phép sửa; dấu `*` dùng cho pattern matching theo tên field. Nó bổ sung ranh giới bảo vệ khỏi mass assignment, chứ không thay cho giới hạn tài nguyên.
- `@InitBinder("orderForm")` áp dụng cho binder của model attribute có tên `orderForm`. Nếu nhiều model attributes/controllers khác cần quy tắc riêng, cần cấu hình đúng phạm vi.
- `@Valid @ModelAttribute("orderForm")` cùng `BindingResult` cho phép kiểm tra các ràng buộc form sau binding nếu có validator phù hợp; không xem validation là giải pháp duy nhất cho tiêu thụ tài nguyên **xảy ra trước validation**.

Controller cần xử lý lỗi phù hợp, kể cả các trường hợp đường dẫn bị từ chối trước khi phương thức handler có thể chạy. Đừng cho rằng mọi thất bại đều chuyển về `BindingResult.hasErrors()` trong mọi cấu hình.

### 7.1. Với JSON @RequestBody

~~~java
@PostMapping("/orders")
ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

Đây là đoạn minh họa. JSON array qua `@RequestBody` thường do `HttpMessageConverter`/Jackson đọc, **không phải** array được mở rộng từ một chuỗi form field name `lines[999].sku` bằng `DataBinder.bind(PropertyValues)`. `autoGrowCollectionLimit` do đó không giới hạn số phần tử được Jackson deserialize trong request body.

Hãy dùng giới hạn request body, DTO với số phần tử tối đa, ràng buộc collection (ví dụ `@Size(max=32)`) và validation lồng nhau thích hợp; bổ sung kiểm soát tài nguyên ở phía parser/proxy khi cần. Lưu ý validation diễn ra **sau** khi payload đã được đọc/deserialized, vì vậy `@Size` không phải trần bộ nhớ trước khi parse.

### 7.2. Nếu mô hình có list lớn hợp lệ thì sao?

Giả sử hệ thống có tới 500 dòng đơn hàng hợp lệ. **Không tự động đặt limit 500 hoặc 1000** chỉ vì muốn một biểu mẫu chứa nhiều dòng; điều đó có thể tạo ra cấp phát lớn từ đầu vào `lines[499].sku` dù chỉ có một field.

Ưu tiên:

1. Thiết kế API nhận collection rõ ràng với giới hạn số phần tử và payload.
2. Giới hạn từng batch thao tác theo nhu cầu thực tế; có thể chia trang hoặc chia batch nếu phù hợp.
3. Kiểm tra quyền và bất biến domain trong service.
4. Chỉ nâng `autoGrowCollectionLimit` khi có bằng chứng nghiệp vụ cần và đã kiểm soát được chi phí tài nguyên.

## 8. Security: giới hạn này quan trọng, nhưng không phải hàng rào toàn năng

### 8.1. Chống cấp phát từ chỉ số thưa

Một client có thể gửi rất ít bytes nhưng một chỉ số cực lớn:

~~~text
lines[999999999].sku=ABC
~~~

Nếu cơ chế binding cố tạo các vị trí trung gian không giới hạn, dữ liệu nhỏ có thể dẫn đến tiêu thụ bộ nhớ lớn. Giới hạn mặc định 256 ra đời để giảm rủi ro này trong những đường binding mà nó có hiệu lực.

Nhưng:

- Ngưỡng này không chặn mọi loại collection (đặc biệt Map keys hoặc collection đặc thù).
- Nó không khống chế mọi nhánh tạo object lồng nhau, độ sâu đường dẫn, số trường form hay JSON array.
- Các collection custom có hành vi `get(index)` khác chuẩn có thể tạo thêm phần tử mà accessor không dự đoán được.
- Direct-field mode có khác biệt quan trọng theo phiên bản; không dùng ngưỡng một cách suy diễn.

Khi nhận input bên ngoài, ưu tiên DTO chỉ gồm field được phép, whitelist property paths, giới hạn kích thước/cấu trúc request, kiểm tra số lượng collection và cập nhật framework được bảo trì.

### 8.2. CVE-2026-59282: trường hợp self-populating List

Ngày 20/08/2026, Spring công bố **CVE-2026-59282**, một tình huống Denial of Service khi property binding xử lý **List có `get(index)` tự sinh phần tử**. Sau khi ngưỡng auto-growth ngăn mở rộng bằng logic của accessor, việc duyệt nested property tiếp tục gọi `list.get(index)`. Với List chuẩn, truy cập vượt phạm vi ném `IndexOutOfBoundsException`; nhưng self-populating List có thể tự cấp phát rất nhiều phần tử khi gặp chỉ số lớn.

Điều kiện rủi ro được Spring mô tả gồm:

1. Ứng dụng cho phép Spring binding sử dụng property paths từ dữ liệu bên ngoài.
2. Object đích chứa **self-populating List**.
3. Element type có thuộc tính con, làm binder cần đi sâu theo dạng `list[index].property`.

Đây **không phải** tuyên bố rằng mọi ứng dụng dùng `ArrayList` đều mắc CVE. Nó cho thấy `autoGrowCollectionLimit` không nhất thiết chặn các hành vi cấp phát nằm **bên trong implementation của collection**.

Theo advisory Spring, các bản `7.0.0–7.0.8`, `6.2.0–6.2.19` và nhiều dòng cũ khác bị ảnh hưởng nếu có đủ điều kiện nêu trên. Bản vá được liệt kê gồm `7.0.9` (OSS) và `6.2.20` (Enterprise Support ở thời điểm công bố), cùng các nhánh hỗ trợ tương ứng. Khi đánh giá hệ thống thực tế, kiểm tra bản vá của phiên bản đang dùng, tránh tạo List tự cấp phát từ index do client chỉ định và không tăng giới hạn mà chưa kiểm soát input.

Nguồn: https://spring.io/security/cve-2026-59282/

### 8.3. Checklist kiểm thử ở mức ứng dụng

| Kiểm tra | Mong đợi |
| --- | --- |
| Gắn `lines[0].sku` hoặc `lines[limit-1].sku` trên list rỗng, auto-grow bật | Hoạt động theo kiểu truy cập và class model phù hợp |
| Gắn `lines[limit].sku` trên list rỗng, bean-property mode | Không tự mở rộng đến chỉ số bằng limit |
| Gắn chỉ số hợp lệ trên list đã có phần tử | Không hiểu nhầm limit thành giới hạn size tuyệt đối |
| Gắn đường dẫn nested khi `autoGrowNestedPaths=false` | Không tự khởi tạo null node |
| Chuyển giữa `initBeanPropertyAccess` và `initDirectFieldAccess` | Test riêng, không suy diễn config parity giữa các Spring version |
| Constructor binding và JSON request | Tự kiểm soát số phần tử, không dựa vào limit của property binding |
| Client gửi field không được phép sửa | Không thay đổi thuộc tính ngoài whitelist/DTO |
| List self-populating | Tránh expose cấu trúc này cho đường dẫn index do client điều khiển; dùng phiên bản đã vá |

## 9. Lỗi diễn giải thường gặp

1. **“Giới hạn mặc định 256 nghĩa là mọi list chỉ có tối đa 256 phần tử.”** Sai: đó là ngưỡng cho **auto-grow** trên đường binding thích hợp, không phải invariant của domain object.
2. **“Giới hạn 32 cho phép chỉ số 32.”** Chỉ số tự mở rộng phải **nhỏ hơn** 32, nếu phần tử chưa tồn tại. Chỉ số 31 là vị trí thứ 32.
3. **“Đặt `autoGrowCollectionLimit` là đã bật auto-grow.”** Cần xét `autoGrowNestedPaths` và khả năng tạo object thực tế.
4. **“Nested path object và list tự mở rộng dùng cùng một giới hạn tổng.”** Limit collection không khống chế tổng độ sâu hoặc số object sinh ra trên toàn bộ cây đối tượng.
5. **“Direct-field access và bean-property access luôn có cùng ngưỡng.”** Sai với những dòng Spring trước 7.1; cần đọc đúng API và test.
6. **“Constructor binding phải chịu ngưỡng này.”** `construct(ValueResolver)` không sử dụng ngưỡng auto-grow của `bind(PropertyValues)`.
7. **“JSON @RequestBody cũng chịu limit này.”** Jackson đọc JSON bằng luồng khác; phải giới hạn request/body/list độc lập.
8. **“Vượt giới hạn chắc chắn tạo một FieldError và HTTP 400.”** Ngoại lệ truy cập đường dẫn có thể phát sinh trước khi lỗi được đưa vào BindingResult; thiết kế handler rõ ràng.
9. **“Đặt limit rất lớn để tránh lỗi.”** Một field thưa có thể kéo theo cấp phát đáng kể; thiết kế API và giới hạn hợp lý trước.
10. **“Setters bị bỏ qua bằng direct-field access thì an toàn hơn.”** Direct field có thể bỏ qua validation/invariants trong setter; chỉ dùng ở ngữ cảnh đã hiểu rõ và tin cậy.
11. **“Dùng @Size là đủ để chặn DoS.”** Validation thường chạy sau binding/deserialization; cần chặn tài nguyên từ lớp nhập liệu trở lên.
12. **“Chỉ cần tránh List chuẩn có chỉ số lớn.”** List chuẩn thường từ chối out-of-range, nhưng custom self-populating List có thể làm điều khác; cần cập nhật bản vá và kiểm tra behavior collection.

## 10. Câu hỏi tự kiểm tra

- Với limit 5 và list đang rỗng, `lines[4].sku` và `lines[5].sku` khác nhau thế nào?
- Vì sao limit 5 không ngăn việc gắn `lines[8].sku` nếu list có sẵn 10 phần tử?
- Khi nào `setAutoGrowNestedPaths(false)` ảnh hưởng đến `customer.address.city` và `lines[2].sku`?
- Vì sao phải đọc đúng phiên bản Spring khi làm việc với `initDirectFieldAccess()`?
- Vì sao `DataBinder.construct(...)` và `@RequestBody` JSON không được bảo vệ bởi limit của property-binding auto-growth?
- Vì sao một self-populating List có thể vượt qua kỳ vọng của lập trình viên dù binder đặt limit thấp?
- Bạn sẽ đặt giới hạn request/body, whitelist trường và validation collection ở tầng nào để tránh biến một field index thành cấp phát lớn?

Bạn có thể thay limit thành 3 hoặc 5 trong ví dụ Java 17+, thử các chỉ số nhỏ 0, 1, 2, 3 và quan sát **size sau binding**, **giá trị field** và **lỗi/ngoại lệ**. Chỉ cần vài giá trị nhỏ là đủ chứng minh nguyên tắc, không cần thử chỉ số hàng triệu.

## Tài liệu tham khảo

- Spring Framework 6.2 DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 7.0 DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework BeanWrapper/property paths: https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
- Spring source DataBinder: https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/validation/DataBinder.java
- Spring source AbstractNestablePropertyAccessor: https://github.com/spring-projects/spring-framework/blob/main/spring-beans/src/main/java/org/springframework/beans/AbstractNestablePropertyAccessor.java
- Spring security advisory CVE-2026-59282: https://spring.io/security/cve-2026-59282/
