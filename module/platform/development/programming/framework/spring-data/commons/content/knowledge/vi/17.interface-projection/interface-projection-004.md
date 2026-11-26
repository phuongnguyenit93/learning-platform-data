# Default method cho giá trị dẫn xuất đơn giản

## 1. Khi projection cần thêm một giá trị để hiển thị

Một interface projection có thể khai báo các getter lấy dữ liệu từ kết quả truy vấn. Đôi khi người gọi còn cần một giá trị đơn giản được tính từ những getter đó: tên hiển thị từ họ và tên, nhãn từ hai thuộc tính hoặc thành tiền từ đơn giá và số lượng.

Nếu phép tính chỉ phụ thuộc vào dữ liệu đã có trong projection, Java default method là một cách biểu đạt trực tiếp:

```java
public interface CustomerNameView {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        String firstName = getFirstName();
        String lastName = getLastName();

        firstName = firstName == null ? "" : firstName.trim();
        lastName = lastName == null ? "" : lastName.trim();

        return (lastName + " " + firstName).trim();
    }
}
```

Trong ví dụ, `firstName` là tên gọi, `lastName` là họ, và quy ước hiển thị của ứng dụng là **họ trước, tên sau**. Với `lastName = "Nguyễn"` và `firstName = "Minh An"`, kết quả là `"Nguyễn Minh An"`.

`getDisplayName()` là phương thức Java có thân, không phải yêu cầu framework tìm thêm một thuộc tính `displayName` trong entity. Nó được tính từ hai getter của projection khi người gọi sử dụng phương thức.

Trong phạm vi **SPRING_DATA_COMMONS**, đây là khả năng của interface projection. Việc query nào tạo được projection, cách lấy dữ liệu và mức tối ưu truy vấn vẫn phụ thuộc mô-đun kho dữ liệu cùng phiên bản đang dùng.

## 2. Điều kiện để dùng default method phù hợp

Một giá trị dẫn xuất thường phù hợp với default method khi đáp ứng các điểm sau:

- Chỉ phụ thuộc vào các accessor mà projection đã cung cấp.
- Phép tính ngắn, rõ ràng và có kết quả xác định từ dữ liệu đầu vào.
- Không cần gọi repository khác, dịch vụ bên ngoài hoặc đọc trạng thái toàn cục.
- Không cần cập nhật entity hay điều khiển transaction.
- Có quy tắc rõ ràng cho dữ liệu thiếu hoặc không hợp lệ.

Ví dụ phù hợp gồm ghép tên, tạo nhãn ngắn hoặc nhân hai giá trị số đã có. Ví dụ cần cân nhắc nơi khác gồm tính giá cuối cùng dựa trên chương trình khuyến mãi, quyền của người dùng hiện tại, tỷ giá trực tuyến hoặc nhiều nguồn dữ liệu.

Default method có từ Java 8. Các ví dụ trong bài sử dụng cú pháp phù hợp với Java 8, nhưng phiên bản Java thực tế của dự án vẫn phải đáp ứng yêu cầu của phiên bản Spring Data đang dùng.

## 3. Phân biệt getter dữ liệu với phương thức dẫn xuất

Trong `CustomerNameView`, ba phương thức có vai trò khác nhau:

| Phương thức | Vai trò | Dữ liệu cần có |
| --- | --- | --- |
| `getFirstName()` | Accessor của projection | Thuộc tính hoặc giá trị ánh xạ `firstName` |
| `getLastName()` | Accessor của projection | Thuộc tính hoặc giá trị ánh xạ `lastName` |
| `getDisplayName()` | Default method tính trong Java | Kết quả của hai accessor trên |

Nếu entity không có thuộc tính `displayName`, việc thêm một getter trừu tượng như sau không tự định nghĩa phép ghép tên:

```java
public interface IncorrectNameView {
    String getFirstName();
    String getLastName();

    // Chưa có thân phương thức hay cơ chế ánh xạ cho giá trị này.
    String getDisplayName();
}
```

Chỉ đặt tên getter không đủ để framework suy ra công thức. Cần một default method, một cơ chế biểu thức được hỗ trợ, hoặc một giá trị đã được query tạo và ánh xạ rõ ràng.

Các getter dữ liệu vẫn phải khớp đúng hợp đồng mapping của truy vấn. Default method không sửa được tên thuộc tính sai, alias thiếu hoặc kiểu dữ liệu không tương thích ở các getter nguồn.

## 4. Ví dụ repository sử dụng projection

Giả sử domain type `Customer` đã được mapping với những thuộc tính sau:

| Thuộc tính | Kiểu minh họa | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh khách hàng |
| `firstName` | `String` | Tên gọi |
| `lastName` | `String` | Họ |
| `status` | `String` | Trạng thái khách hàng |

Projection `CustomerNameView` là một interface riêng cho kết quả đọc. Domain type không cần implement interface này để có thể được chiếu sang nó.

Repository minh họa:

```java
import java.util.List;

import org.springframework.data.repository.Repository;

public interface CustomerRepository extends Repository<Customer, Long> {

    List<CustomerNameView>
    findByStatusOrderByLastNameAscFirstNameAscIdAsc(String status);
}
```

Ví dụ giả định mô-đun và phiên bản hỗ trợ derived query cùng interface projection tương ứng. Mapping của `Customer` và cấu hình repository phải được thiết lập theo kho dữ liệu cụ thể.

Cách sử dụng:

```java
List<CustomerNameView> names =
        repository.findByStatusOrderByLastNameAscFirstNameAscIdAsc("ACTIVE");

for (CustomerNameView name : names) {
    System.out.println(name.getDisplayName());
}
```

Bộ lọc `status` và tiêu chí sort là yêu cầu của query. Projection mô tả những accessor cần cho kết quả đọc. Các thuộc tính dùng trong bộ lọc hoặc sort không nhất thiết đều phải trở thành getter công khai của projection, nếu dạng truy vấn và mô-đun cho phép.

`getDisplayName()` không chạy trong database. Nó được gọi trên từng đối tượng projection khi vòng lặp xử lý kết quả.

## 5. Proxy thực thi default method như thế nào?

Trong cơ chế interface projection thông thường của Spring Data, framework tạo một proxy thực hiện interface được khai báo. Getter dữ liệu được xử lý theo nguồn kết quả, còn default method có thân Java để thực thi.

Luồng sử dụng có thể hình dung như sau:

```text
Caller gọi view.getDisplayName()
    → thực thi thân default method
    → gọi view.getLastName() và view.getFirstName()
    → proxy cung cấp dữ liệu cho từng accessor
    → Java ghép chuỗi và trả giá trị dẫn xuất
```

Có hai hệ quả:

1. Không cần tạo một lớp implementation thủ công chỉ để ghép hai getter.
2. Công thức phải làm việc thông qua hợp đồng projection, không giả định `this` là entity.

Không ép kiểu proxy sang domain type để lấy thêm dữ liệu:

```java
// Không dùng cách này trong projection.
// Customer customer = (Customer) this;
```

Projection là một góc nhìn của dữ liệu. Nếu phép tính cần thêm một thuộc tính nguồn, hãy thể hiện nhu cầu đó bằng accessor hợp lệ và đánh giá lại phạm vi dữ liệu được lấy.

### 5.1. Không mặc định có cache cho giá trị dẫn xuất

Mỗi lần gọi default method có thể thực hiện lại thân phương thức. Không dựa vào giả định rằng framework tự ghi nhớ kết quả của lần gọi đầu tiên.

Một công thức ghép chuỗi đơn giản thường phù hợp với điều này. Một phép tính tốn kém, đọc thời gian hiện tại hoặc gọi tài nguyên bên ngoài sẽ có hành vi và chi phí khó dự đoán hơn nếu getter bị gọi nhiều lần, chẳng hạn trong lúc log hoặc tuần tự hóa.

Interface cũng không cung cấp một trường trạng thái riêng cho từng instance để tự lưu cache theo cách thông thường của một class. Không dùng biến static như cache dùng chung cho các projection khác nhau.

## 6. Quan hệ với closed projection

Một closed projection có các accessor dữ liệu khớp với thuộc tính của aggregate đích. Khi biết rõ dữ liệu nào cần cho projection, Spring Data và mô-đun có thể có cơ hội tối ưu truy vấn.

Default method dẫn xuất từ các accessor có sẵn không tự làm projection trở thành open projection. Trong ví dụ:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        String firstName = getFirstName();
        String lastName = getLastName();

        firstName = firstName == null ? "" : firstName.trim();
        lastName = lastName == null ? "" : lastName.trim();

        return (lastName + " " + firstName).trim();
    }
}
```

Những đầu vào dữ liệu vẫn là `firstName` và `lastName`; không cần một thuộc tính nguồn riêng tên `displayName` chỉ để thực thi phương thức này.

Tuy nhiên, **có khả năng tối ưu không đồng nghĩa bảo đảm mọi truy vấn chỉ đọc đúng hai cột**. Kết quả thực tế phụ thuộc mô-đun, dạng query, mapping, quan hệ dữ liệu và cấu hình. Query viết tường minh cũng có hình dạng kết quả riêng cần đáp ứng.

Không suy ra SQL hoặc lượng dữ liệu đọc chỉ từ việc interface có default method. Khi yêu cầu hiệu năng cụ thể quan trọng, cần quan sát truy vấn thực tế của hệ thống đang chạy.

## 7. So sánh với biểu thức và các nơi tính toán khác

Một open projection có thể dùng `@Value` để tính giá trị bằng biểu thức được hỗ trợ. Chẳng hạn một getter dùng biểu thức truy cập `target` có thể tham chiếu dữ liệu của đối tượng nguồn ngoài những accessor khai báo trực tiếp.

Đối với công thức chỉ dựa vào vài getter đã có, default method thường dễ kiểm tra bằng công cụ Java và không cần biểu thức chuỗi.

| Cách tính | Phù hợp khi | Điều cần cân nhắc |
| --- | --- | --- |
| Default method trong interface projection | Giá trị ngắn, dẫn xuất từ các accessor có sẵn | Giữ phép tính cục bộ, rõ ràng và ít tốn kém |
| Getter dùng `@Value` hoặc SpEL | Cần biểu thức hoặc cơ chế tích hợp tương ứng | Phụ thuộc hỗ trợ, khó xác định đầy đủ đầu vào để tối ưu như closed projection |
| Tính trong query | Cần lọc, sort, tổng hợp hoặc tính toán tại kho dữ liệu | Cú pháp, alias và khả năng thực thi tùy mô-đun |
| Service hoặc assembler tạo DTO | Cần nhiều nguồn, quy tắc nghiệp vụ hoặc định dạng theo ngữ cảnh | Quản lý dependency và phạm vi xử lý rõ ràng |
| Thuộc tính domain được mô hình hóa riêng | Giá trị là một phần của mô hình và cần quản lý vòng đời | Xác định nguồn chân lý, cách cập nhật và tính nhất quán |

Không cần thêm `@Value` chỉ để gọi lại một công thức Java đơn giản đã biểu đạt bằng default method. Cũng không nên đẩy một quy tắc nghiệp vụ phức tạp vào getter chỉ để giữ response ngắn hơn.

## 8. Quy tắc xử lý null phải được chọn có chủ đích

Công thức ghép tên ban đầu có hợp đồng cụ thể:

- `null` ở một thành phần được coi là chuỗi rỗng cho mục đích hiển thị.
- Bỏ khoảng trắng đầu và cuối của từng thành phần bằng `String.trim()`.
- Ghép theo quy ước họ trước, tên sau.
- Nếu cả hai thành phần không có nội dung, trả chuỗi rỗng.

Một số ví dụ:

| `firstName` | `lastName` | `getDisplayName()` |
| --- | --- | --- |
| `"Minh An"` | `"Nguyễn"` | `"Nguyễn Minh An"` |
| `" An "` | `" Nguyễn "` | `"Nguyễn An"` |
| `null` | `"Nguyễn"` | `"Nguyễn"` |
| `"An"` | `null` | `"An"` |
| `"  "` | `null` | `""` |
| `null` | `null` | `""` |

Đây là quy tắc của ví dụ, không phải quy tắc ghép tên mặc định của Spring Data. Nếu sản phẩm yêu cầu cách hiển thị theo locale hoặc cấu trúc tên khác, cần chọn hợp đồng phù hợp thay vì coi tên người luôn chỉ có hai thành phần theo cùng một thứ tự.

`trim()` cũng không phải một cơ chế chuẩn hóa đầy đủ mọi loại khoảng trắng Unicode hay khoảng trắng bên trong tên. Nếu có yêu cầu chuẩn hóa sâu hơn, hãy đặt quy tắc ở nơi có thể dùng lại và kiểm tra rõ ràng.

### 8.1. Không dùng giá trị mặc định để che lỗi mapping

Cần phân biệt dữ liệu thật sự thiếu với accessor không được ánh xạ đúng. Nếu query viết tường minh không trả alias cần thiết hoặc tên thuộc tính sai, trả chuỗi rỗng ở cuối không có nghĩa truy vấn đã đúng.

Khi thấy nhiều giá trị dẫn xuất rỗng bất thường, hãy kiểm tra các getter nguồn trước. Xử lý null ở tầng hiển thị không thay thế kiểm tra mapping và chất lượng dữ liệu.

## 9. Dùng nullable wrapper trong accessor

Spring Data hỗ trợ một số kiểu nullable wrapper trong interface projection, trong đó có `java.util.Optional` theo khả năng tích hợp tương ứng. Với thuộc tính nguồn nullable, wrapper giúp biểu đạt sự thiếu vắng giá trị.

Ví dụ giả định domain type có thuộc tính `email`:

```java
import java.util.Optional;

public interface CustomerContactView {

    Optional<String> getEmail();

    default boolean isContactable() {
        return getEmail()
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .isPresent();
    }
}
```

Trong hợp đồng projection hỗ trợ wrapper, giá trị nguồn có mặt được bọc trong Optional; giá trị nguồn `null` được biểu đạt bằng Optional rỗng. Getter wrapper không được thiết kế để trả `null` thay cho `Optional.empty()`.

`isContactable()` ở đây chỉ nói có một chuỗi email không rỗng sau khi trim. Nó không xác nhận email đúng định dạng, đã được xác minh hay người dùng cho phép liên hệ. Tên và hợp đồng trong ứng dụng thực tế phải phản ánh chính xác mức bảo đảm cần dùng.

Wrapper không làm một thuộc tính chưa tồn tại bỗng trở thành thuộc tính hợp lệ. `getEmail()` vẫn cần một nguồn dữ liệu được ánh xạ đúng.

## 10. Ví dụ số học đơn giản với BigDecimal

Một projection dòng hàng có thể cung cấp đơn giá và số lượng:

```java
import java.math.BigDecimal;

public interface OrderLineView {

    BigDecimal getUnitPrice();

    Integer getQuantity();

    default BigDecimal getLineTotal() {
        BigDecimal unitPrice = getUnitPrice();
        Integer quantity = getQuantity();

        if (unitPrice == null || quantity == null) {
            throw new IllegalStateException(
                    "unitPrice and quantity are required");
        }

        return unitPrice.multiply(
                BigDecimal.valueOf(quantity.longValue()));
    }
}
```

Ví dụ giả định hai thuộc tính đã được mapping và hợp đồng yêu cầu có đủ dữ liệu. Nó chủ động báo lỗi khi thiếu giá trị thay vì tự coi mọi giá trị thiếu là số 0.

Các điểm cần giữ rõ:

- Dùng `BigDecimal` cho phép tính minh họa với số thập phân, không chuyển qua `double` giữa chừng.
- `Integer` cho phép kiểm tra null trước khi sử dụng. Nếu accessor là `int` nhưng nguồn có thể null, lỗi unboxing có thể xảy ra ngay khi gọi getter.
- Kết quả này chỉ là đơn giá nhân số lượng. Thuế, chiết khấu, quy tắc làm tròn và tiền tệ chưa được định nghĩa ở đây.
- Nếu cần tổng hợp nhiều dòng hoặc lọc theo thành tiền tại database, phải thiết kế query hoặc tầng xử lý tương ứng.

Một phép nhân cục bộ có thể phù hợp với default method. Toàn bộ bộ máy tính giá của đơn hàng thường cần một hợp đồng nghiệp vụ riêng.

## 11. Getter dẫn xuất không tự trở thành thuộc tính truy vấn

Giả sử domain type `Customer` không có thuộc tính `displayName`. Việc projection có `getDisplayName()` không làm query sau tự có nghĩa:

```java
// Không suy ra thuộc tính domain từ default method của projection.
List<CustomerNameView> findByDisplayName(String displayName);
```

Derived query được phân tích theo domain model và khả năng của mô-đun, không bằng cách chạy ngược thân Java của default method để tìm một biểu thức database.

Tương tự, không giả định rằng:

```java
Sort.by("displayName");
```

sẽ tự sắp xếp tại database bằng công thức ghép tên trong projection. Query viết tường minh hoặc cơ chế sort theo alias có thể có hỗ trợ riêng ở một số mô-đun, nhưng phải được khai báo và kiểm tra riêng; default method không tạo ra hỗ trợ đó.

Nếu cần lọc hoặc sort theo tên ghép, có thể cân nhắc:

1. Diễn đạt điều kiện hoặc biểu thức tại query bằng cơ chế được mô-đun hỗ trợ.
2. Mô hình hóa một thuộc tính nguồn riêng nếu nghiệp vụ thực sự cần và có cách duy trì nhất quán.
3. Tính và xử lý trong bộ nhớ khi tập dữ liệu đủ nhỏ và hợp đồng cho phép.

Nếu chọn xử lý trong bộ nhớ sau khi phân trang, cần hiểu rằng sắp xếp hoặc lọc lại **một trang** không tương đương sắp xếp hoặc lọc toàn bộ tập dữ liệu trước khi lấy trang. Metadata tổng số và thứ tự giữa các trang cũng không tự được điều chỉnh theo getter dẫn xuất.

## 12. Giữ default method cục bộ và ít phụ thuộc

### 12.1. Không gọi truy vấn cho từng projection

Default method không nên trở thành nơi mở thêm query để lấy dữ liệu còn thiếu. Nếu mỗi hàng lại cần một lần truy cập dữ liệu khác, chi phí có thể tăng theo số hàng và làm người gọi khó thấy nơi phát sinh I/O.

Thay vào đó, hãy thiết kế projection hoặc query đủ dữ liệu cần thiết, hoặc xử lý việc phối hợp nhiều nguồn ở service.

### 12.2. Không giả định mọi getter đều rẻ

Một getter nguồn đơn giản ở tầng interface có thể liên quan đến projection lồng nhau hoặc association. Tùy mô-đun và cách query được xây dựng, truy cập sâu vào quan hệ có thể phát sinh thêm dữ liệu, join hoặc lazy loading.

Một default method chỉ có vài dòng nhưng đi qua nhiều quan hệ chưa chắc là phép tính cục bộ rẻ. Cần đánh giá toàn bộ những accessor mà nó gọi, không chỉ nhìn độ dài thân phương thức.

### 12.3. Không để kết quả phụ thuộc ngầm vào thời gian hoặc người dùng

Các giá trị như tuổi tính theo ngày hiện tại, nhãn theo ngôn ngữ người dùng hoặc giá theo quyền truy cập cần một ngữ cảnh rõ ràng. Đọc thời gian hệ thống hay trạng thái thread ngầm từ getter làm kết quả khó kiểm tra và có thể khác giữa các lần gọi.

Nếu phép tính thực sự cần tham số, có thể thiết kế một phương thức Java có tham số rõ ràng. Tuy nhiên, nó không còn là một getter không tham số mà serializer hay caller có thể sử dụng theo cách thông thường. Với logic hiển thị phụ thuộc nhiều ngữ cảnh, service hoặc assembler tạo DTO thường thể hiện trách nhiệm rõ hơn.

### 12.4. Không dùng default method để cập nhật dữ liệu

Projection phục vụ nhu cầu đọc. Một default getter nên trả giá trị dẫn xuất, thay vì thay đổi entity, gọi `save` hoặc gây hiệu ứng bên ngoài.

Điều này giúp việc gọi getter khi log, debug hoặc tuần tự hóa không vô tình trở thành một thao tác nghiệp vụ có trạng thái.

## 13. Phân biệt default method trong projection và repository

Cả hai đều là cú pháp Java nhưng vai trò khác nhau:

| Vị trí | Ví dụ trách nhiệm | Dữ liệu phương thức làm việc với |
| --- | --- | --- |
| Interface projection | Ghép tên, tạo nhãn từ các getter | Dữ liệu của một đối tượng kết quả đọc |
| Interface repository | Phối hợp hoặc ủy quyền các thao tác repository đã có | Query method và thao tác truy cập dữ liệu |

Thêm default method vào projection không tự tạo một query method mới và không tự thêm transaction interceptor của một service. Nếu getter nguồn phụ thuộc session hoặc lazy association, phạm vi tài nguyên vẫn phải được quản lý ở nơi truy cập và sử dụng dữ liệu.

Cũng không đặt dependency repository hay service vào interface projection bằng biến static để cố tạo cơ chế injection. Khi cần dependency bên ngoài, hãy chọn tầng xử lý phù hợp hoặc cơ chế tích hợp có hợp đồng rõ ràng.

## 14. Kiểm chứng phép tính và việc tích hợp là hai mức khác nhau

### 14.1. Kiểm chứng thân default method bằng Java

Có thể tạo một implementation nhỏ để quan sát công thức mà không cần database:

```java
CustomerNameView view = new CustomerNameView() {
    @Override
    public String getFirstName() {
        return "Minh An";
    }

    @Override
    public String getLastName() {
        return "Nguyễn";
    }
};

System.out.println(view.getDisplayName()); // Nguyễn Minh An
```

Ví dụ này kiểm tra được hành vi Java của default method. Nó không chứng minh query thật đã ánh xạ đúng `firstName` và `lastName`.

### 14.2. Quan sát proxy projection từ dữ liệu trong bộ nhớ

Có thể minh họa cơ chế proxy bằng ProjectionFactory của Spring Data Commons:

```java
import java.util.HashMap;
import java.util.Map;

import org.springframework.data.projection.ProjectionFactory;
import org.springframework.data.projection.SpelAwareProxyProjectionFactory;

ProjectionFactory factory = new SpelAwareProxyProjectionFactory();

Map<String, Object> source = new HashMap<>();
source.put("firstName", "Minh An");
source.put("lastName", "Nguyễn");

CustomerNameView view =
        factory.createProjection(CustomerNameView.class, source);

System.out.println(view.getDisplayName()); // Nguyễn Minh An
```

Dù factory này có khả năng hỗ trợ SpEL, `CustomerNameView` trong ví dụ vẫn dùng default method Java và không có getter `@Value`.

Mức kiểm chứng này cho thấy proxy và default method phối hợp được với một nguồn Map. Nó chưa chứng minh truy vấn database, alias, hiệu năng hoặc transaction của repository thật.

### 14.3. Những ca cần kiểm tra khi tích hợp vào dự án

| Ca | Điều cần xác nhận |
| --- | --- |
| Hai thành phần tên đều có giá trị | Đúng thứ tự và dấu cách theo hợp đồng |
| Một thành phần null hoặc rỗng | Không phát sinh lỗi ngoài dự kiến |
| Cả hai thành phần không có nội dung | Kết quả rỗng hoặc chính sách thay thế đúng yêu cầu |
| Dữ liệu có dấu tiếng Việt | Giá trị được giữ đúng, không tự mất dấu |
| Gọi default method nhiều lần | Kết quả và chi phí phù hợp; không có side effect |
| Query trả interface projection thật | Các getter nguồn ánh xạ đúng |
| Query viết tường minh | Alias hoặc cách mapping đáp ứng accessor cần dùng |
| Getter đi qua quan hệ | Tài nguyên và số lần truy cập dữ liệu chấp nhận được |
| Dùng cùng phân trang hoặc sort | Không hiểu nhầm giá trị Java là thuộc tính query |
| Đưa projection ra response | Serializer biểu diễn các getter đúng hợp đồng API |

Không cần suy ra việc tối ưu truy vấn chỉ từ việc kết quả hiển thị đúng. Nếu có yêu cầu giới hạn dữ liệu đọc, cần quan sát cả phần truy vấn và hành vi của mô-đun.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Framework tìm thuộc tính không tồn tại | Getter dẫn xuất để abstract nhưng không có mapping | Viết default method hoặc định nghĩa nguồn giá trị rõ ràng |
| Ghép tên bị lỗi NullPointerException | Gọi trực tiếp phương thức String trên giá trị nullable | Chọn chính sách null và áp dụng trước khi ghép |
| Kết quả hiện chữ `null` | Nối chuỗi trực tiếp với thành phần null | Chuẩn hóa dữ liệu đầu vào của công thức |
| Giá trị dẫn xuất luôn rỗng | Getter nguồn không có dữ liệu hoặc mapping sai | Kiểm tra từng getter và kết quả query gốc |
| Query theo `displayName` không hợp lệ | Nhầm getter Java với thuộc tính domain | Thiết kế điều kiện query theo khả năng mô-đun |
| Gọi getter làm tăng truy vấn | Truy cập quan hệ hoặc dependency ẩn | Giảm phạm vi getter và thiết kế lại nguồn dữ liệu |
| Tính toán lặp lại tốn thời gian | Giả định getter dẫn xuất được cache | Giữ công thức nhỏ hoặc materialize kết quả ở tầng phù hợp |
| Hiển thị sai thứ tự giữa các trang | Sort lại sau khi đã lấy từng trang | Xác định sort ở query trước khi phân trang |
| Response có thêm các getter nguồn | Serializer xử lý cả accessor và getter dẫn xuất | Chọn DTO hoặc cấu hình response rõ ràng |

## 16. Tình huống tự đánh giá

### A. Chỉ thêm getter tên hiển thị

Entity chỉ có `firstName` và `lastName`. Projection thêm `String getDisplayName()` nhưng không có thân phương thức.

Giải thích vì sao framework không tự biết công thức ghép tên. Viết lại bằng default method có chính sách null rõ ràng.

### B. Tìm kiếm theo getter dẫn xuất

Sau khi tạo `getDisplayName()`, nhóm phát triển thêm `findByDisplayName(...)` vào repository.

Phân biệt domain property với phương thức Java của projection. Đề xuất nơi biểu đạt điều kiện tìm kiếm nếu cần lọc theo tên ghép.

### C. Default method gọi quan hệ lồng nhau

Một getter dẫn xuất đọc `getAddress().getCountry().getName()` cho từng khách hàng và được gọi trong quá trình xuất nhiều bản ghi.

Nêu những giả định về dữ liệu thiếu, tài nguyên và truy cập dữ liệu cần kiểm tra. Giải thích vì sao vài dòng Java chưa đủ để kết luận phép tính rẻ.

### D. Tính tổng đơn hàng trong getter

Nhóm muốn getter tự lấy tỷ giá, chương trình giảm giá đang hoạt động và phí giao hàng từ nhiều dịch vụ.

Xác định những yếu tố đã vượt khỏi phép dẫn xuất đơn giản từ accessor. Chọn nơi đặt logic để dependency và yêu cầu kiểm tra được thể hiện rõ.

### E. Sắp xếp sau khi lấy một trang

Ứng dụng lấy trang thứ hai theo `id`, sau đó sort các projection trong trang bằng `getDisplayName()` và hiển thị như đã sắp xếp toàn bộ khách hàng theo tên.

Giải thích phạm vi thực sự đã được sắp xếp và điều cần thay đổi nếu yêu cầu là thứ tự tên trên toàn bộ tập dữ liệu.

### F. Proxy test đúng nhưng repository trả sai

Ví dụ tạo projection từ Map cho tên hiển thị đúng. Query viết tường minh trong ứng dụng lại trả giá trị nguồn thiếu hoặc sai.

Nêu phần nào đã được ví dụ trong bộ nhớ kiểm chứng và phần nào vẫn cần kiểm tra tích hợp với mô-đun kho dữ liệu.

## 17. Quy trình áp dụng

1. Chọn các getter nguồn đúng với dữ liệu mà projection cần.
2. Đặt công thức ngắn trong default method nếu chỉ phụ thuộc vào các getter đó.
3. Định nghĩa hành vi với null, chuỗi rỗng và dữ liệu không hợp lệ.
4. Giữ phép tính không có side effect, không gọi thêm I/O và không phụ thuộc ngữ cảnh ngầm.
5. Phân biệt rõ giá trị tính bằng Java với thuộc tính dùng trong query.
6. Kiểm tra riêng công thức và việc repository ánh xạ dữ liệu thật.
7. Đánh giá transaction, quan hệ lồng nhau và hiệu năng theo mô-đun đang dùng.

Default method giúp interface projection cung cấp một giá trị dẫn xuất ngay cạnh các accessor nguồn. Cách dùng hiệu quả nhất là giữ công thức nhỏ, hợp đồng đầu vào rõ ràng và trách nhiệm truy vấn ở đúng tầng truy cập dữ liệu.