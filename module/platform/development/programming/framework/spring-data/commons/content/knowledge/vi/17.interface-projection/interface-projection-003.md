# Projection mở bằng @Value và SpEL

## Mục tiêu bài học

Một projection interface có thể cung cấp giá trị không tồn tại nguyên dạng trong đối tượng nguồn, chẳng hạn tên hiển thị được ghép từ tên và họ. Spring Data hỗ trợ cách này bằng `@Value` cùng Spring Expression Language, gọi tắt là SpEL.

Sau bài học, bạn có thể:

- Khai báo projection mở và phân biệt nó với projection đóng.
- Sử dụng `target`, tham số `args` và tham chiếu Spring bean trong biểu thức.
- Chọn giữa SpEL ngắn, default method và logic ánh xạ ở service.
- Giải thích tác động tới khả năng tối ưu truy vấn và thời điểm phát sinh công việc.
- Xử lý giá trị thiếu, lỗi biểu thức và dữ liệu nguồn theo đúng khả năng của từng module.

Bài thuộc chương **Projection interface** của module **SPRING_DATA_COMMONS**. Projection là abstraction dùng chung ở tầng repository; việc chọn trường, tạo query và tải quan hệ vẫn phụ thuộc module lưu trữ. Các ví dụ giả định module đang dùng hỗ trợ interface projection với dạng truy vấn tương ứng.

## 1. Projection mở giải quyết nhu cầu nào?

Giả sử ứng dụng có aggregate `Customer` được mapping hợp lệ:

```text
Customer
├── id: Long
├── tenantId: String
├── givenName: String
├── familyName: String
├── preferredName: String, có thể null
└── address: Address, có thể null
    └── city: String, có thể null
```

Một màn hình chỉ cần id và một chuỗi tên hiển thị. Thay vì bắt mọi caller tự ghép tên, có thể đặt giá trị tính toán lên projection:

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerLabel {

    Long getId();

    @Value("#{target.givenName + ' ' + target.familyName}")
    String getFullName();
}
```

Ở ví dụ đầu tiên, giả sử `givenName` và `familyName` đều khác null. Phần xử lý dữ liệu thiếu được trình bày riêng bên dưới.

Những điểm cần đọc đúng:

- Annotation là `org.springframework.beans.factory.annotation.Value`.
- `#{...}` bao một biểu thức SpEL.
- `target` là đối tượng nguồn đứng sau projection.
- `getFullName()` nhận kết quả tính từ biểu thức; không yêu cầu domain có sẵn thuộc tính `fullName`.
- Interface không cần tự triển khai phương thức này; Spring Data cung cấp proxy lúc chạy.

Một projection interface có accessor dùng `@Value` theo cách này được xem là projection mở. Ngược lại, projection đóng khai báo các accessor cho những thuộc tính đã biết của nguồn. Xem [open projections trong Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.interfaces.open).

### 1.1. Không nhầm với Lombok @Value hoặc placeholder cấu hình

Lombok cũng có annotation tên `Value`, nhưng nó không dùng để gắn biểu thức SpEL cho projection.

Cú pháp placeholder cấu hình như `${app.name}` cũng không thay thế `#{target.givenName}`. Hai cú pháp phục vụ các ngữ cảnh khác nhau; ở đây cần biểu thức truy cập nguồn của projection.

Interface projection không cần được đánh dấu `@Component` chỉ để repository tạo proxy cho nó.

## 2. Dùng projection mở làm kiểu trả về của repository

Khai báo một query method riêng:

```java
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface CustomerRepository extends Repository<Customer, Long> {

    List<CustomerLabel> findByTenantIdOrderByIdAsc(
            String tenantId,
            Pageable pageable);
}
```

Trong ứng dụng đã cấu hình repository và domain:

```java
import java.util.List;

import org.springframework.data.domain.PageRequest;

List<CustomerLabel> rows =
        repository.findByTenantIdOrderByIdAsc(
                tenantId,
                PageRequest.of(0, 20));

for (CustomerLabel row : rows) {
    System.out.println(row.getId());
    System.out.println(row.getFullName());
}
```

Với một khách hàng có:

```text
id         = 42
givenName  = "An"
familyName = "Nguyễn"
```

thì `getFullName()` trả về:

```text
An Nguyễn
```

Thứ tự ghép trong ví dụ là quy tắc hiển thị do ứng dụng lựa chọn. Với sản phẩm cần nhiều quy ước tên khác nhau, không nên coi đây là quy tắc tên người phổ quát.

Repository lọc tenant ngay trong query. Tham số tenant không tự trở thành biến trong biểu thức của `CustomerLabel`.

### 2.1. Giá trị tính toán không tự trở thành dữ liệu lưu trữ

Gọi `getFullName()` không tự:

- Tạo cột `full_name` hoặc trường mới trong document.
- Ghi chuỗi đã ghép trở lại aggregate.
- Cập nhật entity hay kích hoạt auditing như một lần ghi.
- Tạo index cho tên đầy đủ.

Đây là một cách đọc và biểu diễn kết quả. Nếu nghiệp vụ cần lưu tên chuẩn hóa hoặc duy trì dữ liệu dẫn xuất, phải thiết kế riêng quá trình ghi và tính nhất quán.

## 3. Hiểu đúng ngữ cảnh target

Có thể hình dung luồng gọi như sau:

```text
Query của module lưu trữ
    → dữ liệu nguồn
    → proxy CustomerLabel
    → caller gọi getFullName()
    → đánh giá biểu thức với target tương ứng
    → trả chuỗi cho caller
```

`target.givenName` truy cập thuộc tính của nguồn, không phải yêu cầu projection phải có phương thức `getGivenName()`.

Vì vậy, interface chỉ khai báo `getId()` và `getFullName()` vẫn có thể dùng `givenName`, `familyName` trong SpEL khi dữ liệu nguồn thực sự cung cấp được các thuộc tính đó.

### 3.1. target không phải một truy vấn tự động bổ sung dữ liệu

Biểu thức chỉ có thể làm việc với nguồn và ngữ cảnh đánh giá mà hạ tầng cung cấp. Nó không mang hợp đồng “thiếu thuộc tính nào thì tự query đúng thuộc tính đó”.

Tùy module và dạng query, nguồn có thể được xây dựng từ đối tượng domain hoặc cấu trúc kết quả đã ánh xạ. Không mặc định mọi `target` trong mọi truy vấn đều là một entity đầy đủ có cùng kiểu runtime.

Điều này đặc biệt quan trọng khi:

- Viết truy vấn chỉ chọn một số trường.
- Dùng alias cho các giá trị được chọn.
- Truyền toàn bộ `target` cho một helper bean nhận tham số kiểu domain cụ thể.
- Dùng nested property phụ thuộc quan hệ chưa được tải.

Các thuộc tính cần cho biểu thức phải phù hợp với kết quả query thực tế. Chỉ thêm `@Value` không tự sửa một select đang thiếu dữ liệu.

### 3.2. Không dùng tên getter tính toán để suy ra property của nguồn

Trong ví dụ, domain không có `fullName`. Thay biểu thức ghép tên bằng:

```java
@Value("#{target.fullName}")
String getFullName();
```

không tạo ra cách tính mới. Nó yêu cầu nguồn có property `fullName` có thể đọc được.

Nếu cần tái sử dụng cách ghép tên, hãy dùng một helper bean hoặc default method phù hợp, thay vì trỏ về một property chưa tồn tại.

## 4. Dùng args để nhận tham số của phương thức projection

Phương thức dùng SpEL có thể có tham số:

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerGreeting {

    @Value("#{args[0] + ', ' + target.givenName}")
    String getGreeting(String prefix);
}
```

Giả sử nguồn có `givenName = "An"`:

```java
String first = greeting.getGreeting("Chào");
String second = greeting.getGreeting("Xin chào");
```

Kết quả:

```text
Chào, An
Xin chào, An
```

Trong ngữ cảnh này:

| Thành phần | Ý nghĩa |
| --- | --- |
| `target` | Nguồn của projection đang được gọi |
| `args[0]` | Tham số thứ nhất của chính lời gọi `getGreeting(...)` |
| `args[1]` | Tham số thứ hai nếu phương thức projection có tham số đó |
| `@beanName` | Spring bean được phân giải trong ngữ cảnh biểu thức |

`args[0]` ở đây **không phải** tham số thứ nhất của query method repository.

Nếu repository nhận `tenantId` hoặc `Pageable`, những giá trị đó không tự xuất hiện trong mảng `args` khi caller gọi một getter không tham số.

Cũng không giả định serializer sẽ tự biết cần truyền `prefix` nào vào `getGreeting(String)`. Khi phản hồi API cần một lời chào cụ thể, tầng ánh xạ nên chủ động gọi phương thức với giá trị phù hợp.

## 5. Gọi Spring bean để giữ biểu thức ngắn

SpEL phù hợp với biểu thức ngắn. Khi quy tắc cần chuẩn hóa chuỗi, fallback hoặc nhiều nhánh, nên đưa logic sang Java để dễ đọc và kiểm tra.

### 5.1. Bean định dạng tên

```java
import org.springframework.stereotype.Component;

@Component("customerLabelFormatter")
public class CustomerLabelFormatter {

    public String fullName(String givenName, String familyName) {
        String given = normalize(givenName);
        String family = normalize(familyName);
        String label = (given + " " + family).trim();

        return label.isEmpty() ? "Chưa cập nhật" : label;
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }
}
```

Quy tắc của helper:

| givenName | familyName | Kết quả |
| --- | --- | --- |
| `" An "` | `" Nguyễn "` | `"An Nguyễn"` |
| `null` | `"Nguyễn"` | `"Nguyễn"` |
| `"An"` | `null` | `"An"` |
| `null` | `null` | `"Chưa cập nhật"` |
| `"   "` | `""` | `"Chưa cập nhật"` |

### 5.2. Projection gọi helper

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerFormattedLabel {

    Long getId();

    @Value("#{@customerLabelFormatter.fullName(target.givenName, target.familyName)}")
    String getFullName();
}
```

Biểu thức chỉ làm nhiệm vụ nối projection với helper. Tên `customerLabelFormatter` khớp tên bean đã khai báo; phương thức được gọi là public.

Ví dụ truyền hai giá trị chuỗi thay vì buộc helper nhận toàn bộ `Customer`. Cách này làm hợp đồng của helper nhỏ và rõ hơn: nó chỉ cần những gì dùng để định dạng tên.

Vẫn phải bảo đảm query cung cấp được `givenName` và `familyName`. Helper không làm dữ liệu thiếu trong nguồn tự xuất hiện.

Tham chiếu `@...` cần ngữ cảnh có khả năng phân giải bean. Xem [bean references trong SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html). Trong một ví dụ tự tạo projection factory, việc có sẵn object helper trong mã Java chưa tự đăng ký nó vào bean resolver.

### 5.3. Helper bean không làm projection trở thành closed

Projection vẫn có phương thức `@Value`, dù biểu thức chỉ gồm một lời gọi bean.

Spring Data không thể suy ra mọi dependency dữ liệu bên trong Java method chỉ bằng việc nhìn tên bean. Di chuyển logic khỏi chuỗi SpEL giúp tổ chức mã tốt hơn; nó không phục hồi đặc tính tối ưu truy vấn của một closed projection.

Helper nên thực hiện phép tính có đầu vào, đầu ra rõ ràng. Nếu nó tự gọi repository hoặc dịch vụ mạng, một getter tưởng như chỉ đọc dữ liệu có thể trở thành công việc I/O lặp lại cho từng phần tử.

## 6. Xử lý null và thuộc tính lồng nhau

### 6.1. Fallback đơn giản với Elvis

Giả sử muốn dùng tên ưu tiên nếu có:

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerPreferredLabel {

    @Value("#{target.preferredName ?: target.givenName}")
    String getDisplayName();
}
```

Với giá trị chuỗi, toán tử Elvis `?:` của SpEL dùng nhánh sau khi nhánh trước là null hoặc chuỗi rỗng. Nó không tự coi chuỗi chỉ có khoảng trắng là rỗng. Xem [ngữ nghĩa Elvis của Spring Framework](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html).

| preferredName | givenName | Kết quả |
| --- | --- | --- |
| `"Bé An"` | `"An"` | `"Bé An"` |
| `null` | `"An"` | `"An"` |
| `""` | `"An"` | `"An"` |
| `"   "` | `"An"` | Chuỗi khoảng trắng |
| `null` | `null` | `null` |

Nếu hợp đồng yêu cầu luôn có nhãn không rỗng, cần thêm chính sách fallback cuối hoặc dùng helper như phần trước.

### 6.2. Safe navigation cho địa chỉ có thể thiếu

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerCityLabel {

    @Value("#{target.address?.city ?: 'Chưa có thành phố'}")
    String getCityLabel();
}
```

Ở đây:

- `address` null làm phép truy cập `?.city` trả null.
- `city` null hoặc rỗng dẫn tới nhãn mặc định.
- `city` chỉ có khoảng trắng vẫn cần quy tắc chuẩn hóa riêng nếu nghiệp vụ yêu cầu.

Safe navigation bảo vệ phép truy cập cụ thể có thể gặp null; nó không tự làm toàn bộ phần còn lại của một biểu thức phức tạp trở nên null-safe. Với đường dẫn nhiều tầng, xem từng đoạn có thể null. Xem [safe navigation trong SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html).

Ngoài ra, null-safe không có nghĩa là property không tồn tại cũng được xử lý như null. Một property viết sai hoặc không có trong nguồn vẫn cần được sửa theo mapping thực tế.

### 6.3. Tránh biến giá trị thiếu thành dữ liệu có vẻ hợp lệ

Fallback là một quyết định biểu diễn. Nhãn “Chưa cập nhật” không chứng minh dữ liệu gốc đã được sửa.

Nếu tên là thông tin bắt buộc của nghiệp vụ, cần xử lý ở validation hoặc luồng cập nhật dữ liệu. Projection chỉ nên biểu diễn đúng chính sách đã chọn cho trường hợp thiếu.

## 7. Vì sao projection mở ảnh hưởng tới tối ưu truy vấn?

Với một closed projection, các accessor cho biết tập thuộc tính mà proxy cần. Module có thể dùng thông tin đó để tối ưu việc lấy dữ liệu.

Với một biểu thức SpEL, mã có thể đọc các thuộc tính khác nhau của nguồn, đi qua property lồng nhau hoặc gọi bean. Hạ tầng không thể suy ra đầy đủ dependency chỉ từ chữ ký getter.

Do đó, không thể dựa vào open projection để nhận cùng cách tối ưu lựa chọn thuộc tính như closed projection. Điều này không có nghĩa database ngừng sử dụng index, bộ lọc hay các tối ưu khác của nó.

### 7.1. Phân biệt ba tập thuộc tính

Trong ví dụ `CustomerLabel`:

```text
Thuộc tính được đọc để tính tên:
    givenName, familyName

Phương thức projection công khai:
    getId(), getFullName()

Dữ liệu query thực sự lấy:
    do query và module quyết định
```

Ba tập này không nhất thiết trùng nhau.

Một projection chỉ có hai phương thức không chứng minh database chỉ đọc hai cột. Ngược lại, một query chỉ chọn id cũng không tự cung cấp đủ dữ liệu để biểu thức ghép tên thành công.

### 7.2. Truy vấn khai báo vẫn giữ giới hạn của nó

Nếu một truy vấn được khai báo rõ chỉ chọn vài trường, `@Value` không phải chỉ thị bắt query tự mở rộng select để lấy mọi dependency.

Cần kiểm tra:

1. Những thuộc tính biểu thức cần.
2. Những giá trị query thực sự chọn.
3. Alias và tên property mà nguồn projection cung cấp.
4. Kiểu dữ liệu đưa vào helper và kiểu trả về của phương thức.

Ví dụ, nguồn chỉ có một alias `display_label` không tự có hai property `givenName`, `familyName` để biểu thức ghép tên sử dụng.

### 7.3. Chi tiết vẫn thuộc từng store

Trong Spring Data JPA, tài liệu projection giải thích việc dựng interface projection và các giới hạn khi chọn thuộc tính, đặc biệt với đường dẫn lồng nhau có thể dẫn tới join. Không mang một kết luận về câu SQL hay số cột của JPA áp dụng nguyên xi cho document store. Xem [projection trong Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html).

Với một chức năng cụ thể, cần xem query được phát sinh và dữ liệu nguồn. Tên interface hay việc response có ít field chưa đủ để kết luận hiệu năng truy vấn.

## 8. Khi nào default method là lựa chọn phù hợp hơn?

Nếu giá trị tính toán chỉ dùng những accessor có sẵn, có thể dùng Java default method:

```java
import java.util.Objects;

public interface CustomerNames {

    Long getId();

    String getGivenName();

    String getFamilyName();

    default String getFullName() {
        String given =
                Objects.toString(getGivenName(), "").trim();
        String family =
                Objects.toString(getFamilyName(), "").trim();

        String label = (given + " " + family).trim();
        return label.isEmpty() ? "Chưa cập nhật" : label;
    }
}
```

Logic được viết bằng Java, dựa hoàn toàn vào các getter của projection. Không có phương thức `@Value` trong interface này.

Với các accessor nguồn đều khớp domain, một default method tính từ những accessor đó không tự làm projection trở thành open. Module vẫn có thể nhận biết các thuộc tính đầu vào.

So sánh:

| Cách làm | Phù hợp khi | Điều phải chấp nhận |
| --- | --- | --- |
| `@Value` với biểu thức ngắn | Cần một giá trị dẫn xuất đơn giản từ nguồn | Projection mở; biểu thức nằm trong chuỗi |
| `@Value` gọi bean | Quy tắc cần Java helper, có đầu vào rõ | Vẫn là projection mở, có dependency bean |
| Default method | Chỉ cần dữ liệu từ các accessor đã khai báo | Những getter đầu vào cũng nằm trên interface |
| Ánh xạ ở service | Cần phối hợp nhiều nguồn, chính sách hoặc ngữ cảnh ứng dụng | Có thêm bước chuyển đổi rõ ràng |
| Tính trong query của store | Cần lọc, sort hoặc tổng hợp theo giá trị dẫn xuất ở database | Phụ thuộc ngôn ngữ query và khả năng của store |

Không thêm SpEL chỉ vì muốn ghép hai chuỗi. Hãy bắt đầu bằng cách biểu diễn đơn giản nhất đáp ứng yêu cầu về dữ liệu và ranh giới trách nhiệm.

## 9. Getter tính toán không tự dùng được trong derived query và Sort

`getFullName()` là phương thức của projection. Trong domain ví dụ không có property `fullName`.

Vì vậy, khai báo một derived query như:

```java
List<CustomerLabel> findByFullName(String fullName);
```

không có nghĩa parser sẽ đọc biểu thức `@Value`, chuyển nó thành điều kiện rồi tìm theo tên đã ghép.

Tương tự:

```java
Sort.by("fullName");
```

không tự tạo sắp xếp theo `getFullName()` trong SpEL. Thuộc tính sắp xếp phải hợp lệ theo query và mapping được module hỗ trợ.

### 9.1. Cần sort theo tên ghép thì thiết kế ở tầng truy vấn

Các hướng có thể phù hợp:

- Sắp xếp theo các thuộc tính nguồn nếu đúng ý nghĩa nghiệp vụ.
- Dùng biểu thức trong query của store.
- Lưu một khóa hiển thị hoặc khóa chuẩn hóa khi có yêu cầu và cơ chế duy trì nhất quán.
- Chọn một mô hình đọc riêng cho chức năng tìm kiếm.

Mỗi hướng có thể cho thứ tự khác nhau. Ví dụ sort lần lượt theo `givenName`, `familyName` không mặc định tương đương mọi cách chuẩn hóa chuỗi tên đầy đủ.

Cần xét cả collation, quy tắc chữ hoa/thường, dấu và null theo store.

### 9.2. Lọc hoặc sort sau khi phân trang chỉ tác động lên trang đã lấy

Nếu repository đã lấy trang đầu 20 khách hàng rồi ứng dụng mới sort theo `getFullName()`, kết quả chỉ là thứ tự mới của 20 phần tử đó.

Nó không phải trang đầu của toàn bộ khách hàng được sort theo cùng quy tắc.

Nếu chức năng yêu cầu lọc/sort trên toàn tập rồi phân trang, điều kiện đó cần được triển khai ở tầng truy vấn phù hợp trước khi giới hạn kết quả.

### 9.3. Không nhầm SpEL trong projection với SpEL trong query

Cùng sử dụng ngôn ngữ biểu thức không có nghĩa cùng ngữ cảnh:

| Vị trí | Vai trò trong tình huống đang xét |
| --- | --- |
| `@Value` trên phương thức projection | Tính giá trị khi phương thức projection được gọi |
| Biểu thức trong khai báo query được module hỗ trợ | Tham gia xây dựng hoặc ràng buộc truy vấn theo hợp đồng của module |

Không mang nguyên `target` hay mảng `args` của phương thức projection sang ngữ cảnh query rồi kỳ vọng chúng có cùng ý nghĩa.

## 10. Chi phí và lỗi có thể xuất hiện khi gọi getter

Một proxy projection có thể đã được tạo thành công nhưng biểu thức chỉ được đánh giá khi caller truy cập phương thức tương ứng.

Điều đó làm vị trí phát sinh công việc trở nên quan trọng:

```text
Repository trả projection
    → service nhận kết quả
    → mapper hoặc serializer gọi getter
    → SpEL đọc dữ liệu, gọi helper
    → giá trị được tính hoặc lỗi được phát hiện
```

### 10.1. Không giả định giá trị getter đã được memoize

Việc hạ tầng có thể cache biểu thức đã parse không đồng nghĩa kết quả tính của mỗi getter được cache vĩnh viễn.

Hãy thiết kế helper chịu được việc được gọi nhiều lần. Một mapper, một đoạn logging và một serializer có thể cùng truy cập giá trị.

Giả sử một danh sách có 20 phần tử và mỗi phần tử bị gọi getter ba lần. Nếu helper thực hiện một lời gọi mạng mỗi lần, ứng dụng có thể tạo 60 lời gọi thay vì một phép định dạng nhẹ.

Đây là lý do nên giữ getter mang tính đọc, có chi phí dễ dự đoán, và tránh dùng nó để cập nhật trạng thái nghiệp vụ.

### 10.2. Đường dẫn quan hệ có thể làm phát sinh truy vấn phụ

Với JPA, đọc một quan hệ lazy trong biểu thức có thể cần dữ liệu chưa được tải. Hệ quả tùy fetch plan và thời điểm truy cập:

- Trong phạm vi persistence context còn hiệu lực, việc đọc có thể phát sinh query phụ.
- Ngoài phạm vi hợp lệ, việc truy cập dữ liệu chưa tải có thể thất bại.
- Với danh sách nhiều phần tử, các lần đọc quan hệ có thể tạo dạng tải N+1.

Dấu `?.` chỉ xử lý null tại phép truy cập. Nó không làm một quan hệ lazy trở thành dữ liệu đã tải và không thay thế thiết kế fetch plan.

### 10.3. Lỗi chuỗi biểu thức không được Java compiler kiểm tra đầy đủ

Đổi tên `givenName` thành một property khác trong domain không bảo đảm compiler sẽ phát hiện mọi chuỗi SpEL còn dùng tên cũ.

Tương tự, tên bean, tên method helper hoặc số lượng đối số không đúng có thể chỉ bộc lộ khi tạo hoặc sử dụng projection.

Vì vậy, cần có tình huống kiểm tra thật sự gọi các phương thức `@Value`; chỉ khẳng định repository trả được một danh sách chưa đủ.

## 11. Tách projection nội bộ khỏi DTO phản hồi

Một closed projection dùng default method cần khai báo các getter đầu vào. Nếu đưa trực tiếp đối tượng đó cho serializer, các getter đầu vào cũng có thể trở thành field phản hồi theo cấu hình serialization.

Ngược lại, một open projection có ít getter không bảo đảm dữ liệu nguồn được lấy ít hơn.

Có thể tách hai quyết định:

```text
Query và projection:
    cung cấp dữ liệu cần để tính đúng

Tầng ánh xạ:
    chủ động tính những giá trị cần sử dụng

DTO phản hồi:
    chỉ giữ các field thuộc hợp đồng API
```

Ví dụ DTO dùng Java record trong dự án Java 17:

```java
public record CustomerResponse(Long id, String fullName) {

    public static CustomerResponse from(CustomerLabel label) {
        return new CustomerResponse(
                label.getId(),
                label.getFullName());
    }
}
```

Việc gọi `getFullName()` xảy ra rõ tại bước `from`. Nếu biểu thức cần dữ liệu gắn với persistence context, thực hiện ánh xạ trong phạm vi mà dữ liệu đó còn hợp lệ.

DTO không giữ proxy projection nên bước serialization về sau chỉ đọc các giá trị đã được lấy. Điều này cũng giúp quy định rõ đầu ra khi projection nội bộ thay đổi.

Nếu cần dùng locale, thông tin người đang xem hoặc chính sách nhiều bước, tầng ánh xạ/service thường thể hiện ngữ cảnh rõ hơn một chuỗi biểu thức dài.

## 12. Thực hành cơ chế proxy mà không cần database

Có thể minh họa biểu thức ngắn bằng `SpelAwareProxyProjectionFactory` của Spring Data Commons.

Đoạn dưới sử dụng `CustomerLabel` đã khai báo ở phần đầu và một `Map` làm nguồn:

```java
import java.util.Map;

import org.springframework.data.projection.SpelAwareProxyProjectionFactory;

SpelAwareProxyProjectionFactory factory =
        new SpelAwareProxyProjectionFactory();

CustomerLabel label = factory.createProjection(
        CustomerLabel.class,
        Map.of(
                "id", 42L,
                "givenName", "An",
                "familyName", "Nguyễn"));

System.out.println(label.getId());       // 42
System.out.println(label.getFullName()); // An Nguyễn

System.out.println(
        factory.getProjectionInformation(CustomerLabel.class)
                .isClosed());           // false
```

Factory hỗ trợ các phương thức projection có `@Value`; xem [API SpelAwareProxyProjectionFactory](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/projection/SpelAwareProxyProjectionFactory.html).

Ví dụ này giúp quan sát:

- Cách một interface được tạo thành projection proxy.
- Việc biểu thức đọc các giá trị từ nguồn.
- Metadata cho biết projection không closed.

Nó không xác minh số cột SQL, mapping repository, lazy loading hay khả năng projection của một store.

Với projection gọi `@customerLabelFormatter`, cần dùng factory có BeanFactory phù hợp hoặc kiểm tra trong Spring context đã đăng ký helper. Factory tự tạo trong đoạn trên chỉ minh họa biểu thức không tham chiếu bean.

## 13. Các tình huống cần kiểm tra trong ứng dụng

| Tình huống | Điều cần xác minh |
| --- | --- |
| Tên và họ đều có dữ liệu | Chuỗi được ghép đúng thứ tự và định dạng |
| Một tên null hoặc rỗng | Fallback khớp chính sách |
| Tên chỉ chứa khoảng trắng | Có chuẩn hóa như mong muốn hay không |
| Gọi cùng projection với hai prefix khác nhau | `args` lấy từ lời gọi phương thức hiện tại |
| Đổi tên helper bean hoặc property | Có phát hiện lỗi trong luồng gọi getter |
| Query chỉ chọn một số trường | Nguồn có đủ dependency của biểu thức |
| Đọc một quan hệ từ SpEL | Số query và phạm vi persistence context |
| Gọi getter nhiều lần | Không có tác động phụ hoặc I/O ngoài dự kiến |
| Trả kết quả qua API | DTO/serializer tạo đúng các field đã định |
| Phân trang và sort theo giá trị dẫn xuất | Thứ tự đúng trên toàn tập theo yêu cầu |

Khi kiểm tra hiệu năng, quan sát riêng thời gian query, công việc ánh xạ và công việc khi gọi getter. Một phép đo chỉ bao quanh lời gọi repository có thể chưa gồm chi phí SpEL hay helper xảy ra về sau.

### 13.1. Phân biệt những nguyên nhân thường bị gộp chung

| Biểu hiện | Nguyên nhân có thể có | Hướng xác định |
| --- | --- | --- |
| Getter tính toán không chạy như mong đợi | Import nhầm annotation hoặc dùng sai cú pháp | Kiểm tra import và biểu thức |
| Không phân giải được helper | Tên bean sai hoặc ngữ cảnh không có bean resolver | Kiểm tra đăng ký bean và factory |
| Lỗi đọc property | Tên không khớp nguồn hoặc query thiếu dữ liệu | So sánh biểu thức với nguồn thực tế |
| Helper nhận sai kiểu đối số | Giả định target luôn là một domain class cụ thể | Kiểm tra kiểu nguồn và hợp đồng helper |
| Lỗi khi serialize | Getter được gọi muộn và cần dữ liệu chưa sẵn sàng | Ánh xạ DTO trong phạm vi phù hợp |
| Query lấy nhiều dữ liệu hơn dự kiến | Đang dùng open projection hoặc fetch plan khác giả định | Quan sát query, không suy từ số getter |
| Sort theo tên đầy đủ bị sai toàn cục | Sort ở Java sau khi đã giới hạn trang | Thiết kế lại thứ tự tại tầng truy vấn |

Không kết luận mọi lỗi của getter đều là “SpEL không hỗ trợ”. Vấn đề có thể nằm ở dữ liệu, query, bean context hoặc vòng đời của nguồn.

## 14. Câu hỏi tự kiểm tra

### Câu 1: Có cần property fullName trong domain không?

Projection có `@Value("#{target.givenName + ' ' + target.familyName}")` trên `getFullName()`. Domain chỉ có `givenName`, `familyName`. Cách này có hợp lý không?

**Trả lời:** Có, nếu nguồn của projection cung cấp được hai thuộc tính đó và module hỗ trợ dạng projection đang dùng. Giá trị được tính bởi biểu thức; không cần lưu sẵn property `fullName`.

### Câu 2: args[0] là tenantId phải không?

Repository có tham số đầu tiên là `tenantId`. Projection khai báo `getGreeting(String prefix)` dùng `args[0]`. Khi gọi `getGreeting("Chào")`, `args[0]` là gì?

**Trả lời:** Là `"Chào"`, tham số của chính phương thức projection. Nó không tự nhận tham số repository.

### Câu 3: Chuyển logic sang bean có phục hồi tối ưu closed projection không?

Biểu thức chỉ còn `@customerLabelFormatter.fullName(...)`. Hạ tầng có thể xem nó là closed projection không?

**Trả lời:** Không. Phương thức vẫn dùng `@Value`; dependency ẩn trong Java method không tự trở thành tập thuộc tính mà query engine suy ra được.

### Câu 4: Elvis có xử lý khoảng trắng không?

`preferredName` bằng ba dấu cách. Biểu thức `target.preferredName ?: target.givenName` có tự dùng `givenName` không?

**Trả lời:** Không đối với giá trị chuỗi này. Elvis xử lý null hoặc chuỗi rỗng, còn chuẩn hóa khoảng trắng cần được viết rõ.

### Câu 5: Có thể sort database theo getter tính toán không?

Projection có `getFullName()` dùng SpEL, domain không có property tương ứng. `Sort.by("fullName")` có tự chuyển SpEL thành câu sort không?

**Trả lời:** Không. Cần biểu diễn yêu cầu sort bằng mapping/query được store hỗ trợ, hoặc chọn mô hình dữ liệu phù hợp.

### Câu 6: Default method có luôn làm projection mở không?

Interface có `getGivenName()`, `getFamilyName()` khớp domain và default method ghép hai getter. Có bắt buộc mất đặc tính closed không?

**Trả lời:** Không. Logic tính từ accessor đã khai báo có thể dùng default method mà không thêm `@Value`; module vẫn có thể biết các thuộc tính đầu vào.

### Câu 7: Có projection proxy là đủ kiểm tra chưa?

Query đã trả được danh sách nhưng ứng dụng chưa gọi getter `@Value`. Có thể coi biểu thức và helper đều hoạt động đúng không?

**Trả lời:** Chưa. Cần thực sự gọi các phương thức tính toán với dữ liệu đại diện, đồng thời kiểm tra mapping và query trong tích hợp store.

## Những điểm cần nhớ

- `@Value` trên phương thức projection dùng SpEL để cung cấp giá trị dẫn xuất; đó là projection mở.
- `target` là nguồn, `args` là tham số lời gọi phương thức projection, còn `@name` tham chiếu bean.
- Projection mở không mang lại khả năng suy ra tập thuộc tính cần lấy như closed projection.
- Biểu thức ngắn giúp đọc mã; logic nhiều nhánh nên nằm trong Java helper hoặc tầng ánh xạ.
- Default method phù hợp khi chỉ cần những accessor đã khai báo.
- Getter SpEL không tự trở thành điều kiện lọc, thứ tự sort hay field được lưu trong database.
- Xác định riêng khả năng của store, dữ liệu nguồn, thời điểm gọi getter và hợp đồng DTO bên ngoài.
