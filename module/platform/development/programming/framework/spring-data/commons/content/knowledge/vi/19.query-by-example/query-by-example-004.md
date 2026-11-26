# Ảnh hưởng của kiểu nguyên thủy lên điều kiện mẫu

Trong Spring Data Commons, Query by Example (QBE) tạo điều kiện tìm kiếm từ một đối tượng mẫu, gọi là **probe**, và quy tắc so khớp trong `ExampleMatcher`. Một chi tiết dễ gây sai kết quả là thuộc tính kiểu nguyên thủy của Java luôn có giá trị: `boolean` có thể là `false`, còn `int` có thể là `0`, ngay cả khi người lập trình chưa gọi setter.

Vì vậy, một probe tưởng như chỉ chứa quốc gia có thể đồng thời yêu cầu khách hàng chưa kích hoạt và có mức ưu tiên bằng không. Bài học này giải thích cơ chế đó và cách xây dựng điều kiện mẫu đúng với ý định tìm kiếm.

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

- Giải thích vì sao kiểu nguyên thủy làm xuất hiện điều kiện ngoài ý muốn trong QBE.
- Phân biệt giá trị mặc định của Java, giá trị nghiệp vụ và trạng thái không truyền bộ lọc.
- Chọn giữa kiểu bao như `Boolean`, `Integer` và việc bỏ qua đường dẫn thuộc tính.
- Tạo `Example` từ DTO tìm kiếm mà vẫn lọc được chính xác `false` và `0`.
- Nhận biết giới hạn thuộc về mapping và từng module Spring Data khi áp dụng ví dụ.

`Example`, `ExampleMatcher` và `QueryByExampleExecutor` là abstraction dùng chung của Spring Data. Khả năng thực thi QBE, loại thuộc tính được hỗ trợ và cách chuyển điều kiện xuống kho dữ liệu phụ thuộc module cụ thể. Những biểu thức điều kiện trong bài mô tả ý nghĩa logic, không khẳng định mọi kho dữ liệu đều sinh SQL giống nhau.

## 2. QBE quan sát giá trị hiện tại, không quan sát lịch sử gọi setter

Một `Example<T>` kết hợp hai thành phần:

```java
Example<T> example = Example.of(probe, matcher);
```

- **Probe** cung cấp các giá trị để so khớp.
- **Matcher** quy định cách đưa thuộc tính vào điều kiện, bỏ qua đường dẫn nào, xử lý `null` và kết hợp điều kiện ra sao.

Mặc định, QBE bỏ qua các thuộc tính có giá trị `null`. Nhưng kiểu nguyên thủy không thể mang `null`, nên các thuộc tính nguyên thủy được ánh xạ và được QBE hỗ trợ vẫn tham gia so khớp nếu không bị loại trừ rõ ràng.

QBE không tự phân biệt hai đoạn mã sau về giá trị của `active`:

```java
Customer first = new Customer();

Customer second = new Customer();
second.setActive(false);
```

Nếu `active` là `boolean` không có giá trị khởi tạo riêng, cả hai đối tượng đều có `active == false`. Probe không chứa thông tin rằng đối tượng thứ nhất chưa được gọi setter, còn đối tượng thứ hai được chủ động đặt thành `false`.

Điểm cần nhớ là **không gán giá trị trong mã nguồn không đồng nghĩa với không tham gia điều kiện QBE**.

## 3. Giá trị mặc định của thuộc tính Java

Bảng sau áp dụng cho **field của đối tượng** khi không có initializer, constructor hay cơ chế khởi tạo khác thay đổi giá trị:

| Kiểu thuộc tính | Giá trị mặc định | Ý nghĩa khi được đưa vào QBE |
| --- | --- | --- |
| `boolean` | `false` | Tìm thuộc tính có giá trị `false` |
| `byte`, `short`, `int` | `0` | Tìm thuộc tính bằng không |
| `long` | `0L` | Tìm thuộc tính bằng không |
| `float`, `double` | `0.0` | Dùng giá trị số không làm giá trị mẫu, nếu kiểu được hỗ trợ |
| `char` | `'\u0000'` | Dùng ký tự mặc định làm giá trị mẫu, nếu kiểu được hỗ trợ |
| `Boolean`, `Integer`, `Long` và các kiểu bao khác | `null` | Được bỏ qua với chính sách mặc định bỏ qua `null` |
| `String` và các kiểu tham chiếu khác | `null` | Được bỏ qua với chính sách mặc định bỏ qua `null` |

Quy tắc giá trị mặc định của field không áp dụng cho biến cục bộ chưa được khởi tạo. Java yêu cầu biến cục bộ có giá trị trước khi được đọc.

Ngoài ra, `0`, `false` và ký tự rỗng mặc định không phải chỉ thị đặc biệt của QBE. Chúng là các giá trị thực. Tương tự, chuỗi rỗng `""` không tự trở thành `null` và không được bảo đảm sẽ bị bỏ qua.

### 3.1. Giá trị thực tế có thể khác mặc định của Java

Xét khai báo:

```java
private boolean active = true;
private int priority = 1;
```

Một probe vừa khởi tạo có thể mang `active == true` và `priority == 1`. Các giá trị đó cũng có thể tham gia điều kiện. QBE đọc trạng thái hiện tại của probe, dù trạng thái xuất phát từ initializer, constructor, builder hay setter.

Do đó, thay `0` bằng một giá trị mặc định nghiệp vụ khác không giải quyết được vấn đề bộ lọc tùy chọn.

## 4. Ví dụ: chỉ muốn tìm quốc gia nhưng vô tình thêm hai điều kiện

Giả sử ứng dụng có kiểu dữ liệu `Customer` với các thuộc tính sau. Để tập trung vào Spring Data Commons, ví dụ lược bỏ annotation mapping; ứng dụng thực tế cần khai báo mapping phù hợp với module lưu trữ đang dùng.

```java
public class Customer {

    private Long id;
    private String country;
    private boolean active;
    private int priority;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getCountry() {
        return country;
    }

    public void setCountry(String country) {
        this.country = country;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }

    public int getPriority() {
        return priority;
    }

    public void setPriority(int priority) {
        this.priority = priority;
    }
}
```

Tạo mẫu tìm kiếm:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setCountry("VN");

ExampleMatcher matcher = ExampleMatcher.matchingAll();
Example<Customer> example = Example.of(probe, matcher);
```

Với giả định các thuộc tính trên được ánh xạ bình thường và được module hỗ trợ, probe có trạng thái:

| Thuộc tính | Giá trị hiện tại | Tham gia điều kiện? |
| --- | --- | --- |
| `id` | `null` | Không, vì mặc định bỏ qua `null` |
| `country` | `"VN"` | Có |
| `active` | `false` | Có |
| `priority` | `0` | Có |

Ý định ban đầu là chỉ lọc quốc gia. Điều kiện logic thực tế lại tương đương:

```text
country khớp "VN"
AND active = false
AND priority = 0
```

Cách so khớp `String` cụ thể còn phụ thuộc matcher và module. Điểm quan trọng trong ví dụ là sự xuất hiện của hai điều kiện số và boolean ngoài ý muốn.

Nếu repository hỗ trợ `QueryByExampleExecutor<Customer>`, có thể thực thi mẫu thông qua:

```java
Iterable<Customer> result = customerRepository.findAll(example);
```

`customerRepository` ở đây là repository do ứng dụng cấu hình với module hỗ trợ QBE. Không phải mọi repository hay mọi kho dữ liệu đều mặc nhiên có cùng khả năng này.

## 5. Vì sao bỏ qua null không loại được false và 0?

Đây là cách sửa thường gặp nhưng không giải quyết nguyên nhân:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues();
```

`withIgnoreNullValues()` chỉ tác động đến thuộc tính có giá trị `null`. Trong probe trên:

```text
active   = false  → không phải null
priority = 0      → không phải null
```

Vì vậy, cả hai vẫn có thể tạo điều kiện.

`withIncludeNullValues()` cũng không biến kiểu nguyên thủy thành bộ lọc tùy chọn. Nó yêu cầu đưa cả các thuộc tính có giá trị `null` vào so khớp theo khả năng của module, có thể tạo thêm điều kiện đối với `id`, `country` hoặc các thuộc tính tham chiếu khác.

Một hệ quả liên quan: với matcher bỏ qua `null`, dùng kiểu bao và đặt giá trị `null` diễn đạt **không áp dụng bộ lọc đó**. Nó không diễn đạt yêu cầu **tìm các bản ghi có thuộc tính null**. Hai nhu cầu này phải được thiết kế riêng; không nên bật đưa mọi giá trị null vào điều kiện nếu chỉ muốn tìm null trên một thuộc tính.

## 6. Cách 1: bỏ qua rõ ràng thuộc tính không dùng để tìm kiếm

Nếu thao tác hiện tại chỉ tìm theo quốc gia, hãy loại các field nguyên thủy khỏi mẫu:

```java
Customer probe = new Customer();
probe.setCountry("VN");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues()
    .withIgnorePaths("active", "priority");

Example<Customer> example = Example.of(probe, matcher);
```

Ý nghĩa điều kiện còn lại:

```text
country khớp "VN"
```

`withIgnorePaths(...)` nhận **đường dẫn thuộc tính của domain object**, không phải tên cột trong cơ sở dữ liệu. Nếu field Java là `active` nhưng cột lưu trữ là `is_active`, đường dẫn cần dùng vẫn là `active`.

Cách này phù hợp khi:

- Domain giữ kiểu nguyên thủy để bảo đảm invariant nghiệp vụ.
- Màn hình tìm kiếm chỉ hỗ trợ một tập thuộc tính rõ ràng.
- Một số giá trị trên probe có sẵn do constructor nhưng không thuộc điều kiện tìm kiếm.

Cần chú ý khi tái sử dụng matcher: nếu một matcher luôn bỏ qua `active`, việc gọi `probe.setActive(true)` không làm `active` quay lại điều kiện. Giá trị có trên probe vẫn bị quy tắc bỏ qua đường dẫn loại trừ.

`ExampleMatcher` là bất biến. Các phương thức cấu hình trả về matcher mới, vì vậy phải dùng kết quả trả về:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
matcher = matcher.withIgnorePaths("active", "priority");
```

Nếu chỉ gọi `matcher.withIgnorePaths(...)` rồi bỏ kết quả, biến `matcher` cũ không nhận cấu hình mới.

## 7. Cách 2: dùng kiểu bao khi mô hình thực sự cho phép vắng giá trị

Nếu một thuộc tính trong đối tượng dùng làm probe có thể biểu diễn trạng thái chưa có giá trị, kiểu bao hỗ trợ ba trạng thái cần thiết:

| Thuộc tính kiểu bao | Giá trị | Ý nghĩa với matcher bỏ qua null |
| --- | --- | --- |
| `Boolean active` | `null` | Không lọc theo trạng thái kích hoạt |
| `Boolean active` | `false` | Lọc khách hàng chưa kích hoạt |
| `Boolean active` | `true` | Lọc khách hàng đã kích hoạt |
| `Integer priority` | `null` | Không lọc theo ưu tiên |
| `Integer priority` | `0` | Lọc mức ưu tiên bằng không |
| `Integer priority` | Một số khác | Lọc theo đúng giá trị đó |

Ví dụ, nếu domain được thiết kế với kiểu bao và không gán giá trị mặc định:

```java
public class CustomerProfile {
    private String country;
    private Boolean active;
    private Integer priority;

    // Getter và setter tương ứng với ba thuộc tính.
}
```

Một probe mới chỉ đặt `country` sẽ để hai thuộc tính còn lại là `null`, nên chúng được bỏ qua theo mặc định.

Tuy nhiên, đổi domain từ `boolean` sang `Boolean` chỉ để tiện tìm kiếm có thể làm thay đổi invariant, xử lý null, mapping và các luồng ghi dữ liệu. Chỉ dùng kiểu bao trong domain nếu điều đó phù hợp với mô hình. Một DTO tìm kiếm riêng thường phù hợp hơn khi entity vẫn cần giá trị bắt buộc.

Không thể chỉ tạo DTO bất kỳ rồi mặc nhiên truyền DTO đó vào repository của entity: kiểu probe phải tương thích với domain type mà repository QBE hỗ trợ. DTO nên được chuyển thành probe của domain, đồng thời tạo matcher tương ứng.

## 8. Cách 3: DTO tùy chọn, domain nguyên thủy, matcher được xây dựng theo dữ liệu đầu vào

Đây là cách tách rõ dữ liệu tìm kiếm khỏi dữ liệu lưu trữ:

- DTO dùng `Boolean` và `Integer` để giữ được thông tin người dùng có truyền bộ lọc hay không.
- Domain tiếp tục dùng `boolean` và `int`.
- Khi DTO có giá trị, đặt giá trị đó lên probe.
- Khi DTO không có giá trị, thêm đường dẫn tương ứng vào danh sách bỏ qua.

### 8.1. Khai báo bộ lọc

Ví dụ dưới đây dùng cú pháp `record` của Java 17 trở lên; có thể thay bằng DTO class thông thường nếu dự án dùng phiên bản Java khác.

```java
public record CustomerFilter(
    String country,
    Boolean active,
    Integer priority
) {}
```

Quy ước đầu vào trong ví dụ:

```text
country = null   → không lọc quốc gia
active = null    → không lọc trạng thái kích hoạt
priority = null  → không lọc mức ưu tiên
```

Nếu ứng dụng muốn coi chuỗi trắng là không truyền giá trị, cần chuẩn hóa nó rõ ràng tại biên nhận đầu vào hoặc trong bộ chuyển đổi. QBE không tự bảo đảm quy tắc đó.

### 8.2. Tạo Example từ bộ lọc

Đoạn mã sau dùng lớp `Customer` ở phần trước:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

public final class CustomerExamples {

    private CustomerExamples() {}

    public static Example<Customer> from(CustomerFilter filter) {
        Customer probe = new Customer();
        probe.setCountry(filter.country());

        List<String> ignoredPaths = new ArrayList<>();

        if (filter.active() != null) {
            probe.setActive(filter.active());
        } else {
            ignoredPaths.add("active");
        }

        if (filter.priority() != null) {
            probe.setPriority(filter.priority());
        } else {
            ignoredPaths.add("priority");
        }

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreNullValues();

        if (!ignoredPaths.isEmpty()) {
            matcher = matcher.withIgnorePaths(
                ignoredPaths.toArray(new String[0])
            );
        }

        return Example.of(probe, matcher);
    }
}
```

Phương thức giả định `filter` không null. Việc kiểm tra tính hợp lệ của DTO, chẳng hạn giới hạn miền giá trị `priority`, thuộc bước xác thực đầu vào của ứng dụng.

Cách sử dụng:

```java
// Chỉ lọc quốc gia; active và priority bị bỏ qua.
Example<Customer> byCountry = CustomerExamples.from(
    new CustomerFilter("VN", null, null)
);

// Lọc khách hàng chưa kích hoạt; priority bị bỏ qua.
Example<Customer> inactive = CustomerExamples.from(
    new CustomerFilter("VN", false, null)
);

// Lọc ưu tiên đúng bằng 0; active bị bỏ qua.
Example<Customer> zeroPriority = CustomerExamples.from(
    new CustomerFilter("VN", null, 0)
);
```

Ở đây, kiểm tra `!= null` là điểm quyết định. Không dùng giá trị `true` hoặc số dương để nhận diện việc người dùng có truyền bộ lọc.

### 8.3. Hai cách kiểm tra đầu vào sai

```java
if (Boolean.TRUE.equals(filter.active())) {
    probe.setActive(true);
}
```

Điều kiện trên chỉ nhận `true`, nên không đủ để triển khai một bộ lọc có cả lựa chọn `false`. Nếu phần còn lại của mã bỏ qua `active` khi nhánh không chạy, yêu cầu tìm `false` sẽ bị mất.

Tương tự:

```java
if (filter.priority() != null && filter.priority() > 0) {
    probe.setPriority(filter.priority());
}
```

Đoạn mã này loại `0`, dù `0` có thể là một mức ưu tiên hợp lệ. Nếu miền nghiệp vụ cho phép số âm, nó cũng làm mất các giá trị đó. Kiểm tra có truyền dữ liệu và kiểm tra giá trị hợp lệ là hai việc riêng.

## 9. Đối chiếu bằng một bộ dữ liệu nhỏ

Giả sử kho dữ liệu có các bản ghi sau, với so khớp quốc gia theo đúng mã quốc gia:

| Khách hàng | country | active | priority |
| --- | --- | --- | --- |
| C01 | VN | `true` | `0` |
| C02 | VN | `false` | `0` |
| C03 | VN | `false` | `2` |
| C04 | TH | `false` | `0` |
| C05 | VN | `true` | `2` |

Các kết quả logic mong đợi:

| Cách tạo mẫu | Điều kiện hiệu lực | Kết quả |
| --- | --- | --- |
| `new Customer()`, chỉ đặt `country = "VN"`, không bỏ qua field | Quốc gia VN, chưa kích hoạt, ưu tiên 0 | C02 |
| Đặt quốc gia VN và bỏ qua `active`, `priority` | Quốc gia VN | C01, C02, C03, C05 |
| `CustomerFilter("VN", false, null)` qua bộ chuyển đổi | Quốc gia VN, chưa kích hoạt | C02, C03 |
| `CustomerFilter("VN", null, 0)` qua bộ chuyển đổi | Quốc gia VN, ưu tiên 0 | C01, C02 |
| `CustomerFilter("VN", true, 0)` qua bộ chuyển đổi | Quốc gia VN, đã kích hoạt, ưu tiên 0 | C01 |

Bảng này cho thấy việc bỏ qua một field và việc lọc field bằng giá trị mặc định tạo ra hai tập kết quả khác nhau.

Khi DTO có mọi thuộc tính bằng `null`, bộ chuyển đổi trên tạo mẫu không còn điều kiện nghiệp vụ trên các thuộc tính đã nêu. Nếu module chấp nhận mẫu rỗng, nó có thể trả về toàn bộ tập dữ liệu mà truy vấn được phép nhìn thấy. Ứng dụng cần quyết định rõ tìm kiếm không có bộ lọc có được phép hay không, đồng thời áp dụng phân trang phù hợp. Các ràng buộc quyền truy cập phải được thực thi độc lập, không dựa vào việc người dùng có truyền bộ lọc QBE.

## 10. Không đổi sang matchingAny để chữa điều kiện thừa

`matchingAll()` kết hợp các điều kiện được chọn theo ý nghĩa AND. `matchingAny()` kết hợp theo ý nghĩa OR; nó không xóa các điều kiện ngoài ý muốn.

Nếu probe có:

```text
country = "VN"
active = false
priority = 0
```

thì `matchingAny()` có thể tạo ý nghĩa:

```text
country khớp "VN"
OR active = false
OR priority = 0
```

Trong bộ dữ liệu ở phần trước, cả C04 ở quốc gia TH cũng thỏa điều kiện. Việc thay đổi cách kết hợp làm mở rộng kết quả, không khôi phục ý định chỉ lọc quốc gia.

Muốn bỏ một điều kiện, hãy bỏ qua đúng thuộc tính hoặc thiết kế trạng thái vắng giá trị phù hợp.

## 11. Các trường hợp cần quan sát thêm trên probe

### 11.1. ID kiểu nguyên thủy

Nếu domain khai báo `long id`, một probe mới có thể mang `id == 0`. Khi thuộc tính ID được module đưa vào QBE, giá trị này có thể tạo thêm điều kiện ID bằng không.

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id", "active", "priority");
```

Chỉ bỏ qua những thuộc tính không thuộc thao tác tìm kiếm hiện tại. Nếu người dùng thực sự tìm theo ID, điều kiện ID phải được giữ lại và xác thực đúng.

Việc ID có được sinh tự động khi lưu không có nghĩa QBE sẽ tự bỏ qua ID trên probe. Cơ chế sinh ID khi ghi và cơ chế tạo điều kiện tìm kiếm là hai cơ chế khác nhau. Cần đối chiếu mapping cùng khả năng QBE của module đang sử dụng.

### 11.2. Đối tượng lồng nhau

Một thuộc tính lồng nhau có thể không tham gia khi đối tượng chứa nó đang là `null`. Nhưng nếu mã khởi tạo sẵn đối tượng đó, các field nguyên thủy bên trong cũng có giá trị mặc định.

Ví dụ, nếu `address` được khởi tạo và có `int buildingNumber`, probe có thể mang `address.buildingNumber == 0`. Với đường dẫn lồng nhau được module hỗ trợ, cần xem xét bỏ qua:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("address.buildingNumber");
```

Ví dụ này không bảo đảm mọi module đều hỗ trợ mọi loại association hay cấu trúc lồng nhau. Trước hết cần xác định thuộc tính nào thực sự được mapping và có thể dùng trong QBE của kho dữ liệu đó.

### 11.3. Chuyển đổi hoặc binding làm mất thông tin đầu vào

Nếu DTO nhận request đã dùng `boolean active`, thông tin không truyền `active` có thể đã biến thành `false` ngay tại bước tạo DTO. Khi ấy, việc chuyển tiếp sang probe không thể tự khôi phục thông tin đã mất.

Đối với bộ lọc tùy chọn, giữ khả năng biểu diễn sự vắng mặt từ đầu bằng kiểu bao hoặc một cơ chế theo dõi sự hiện diện rõ ràng. Nếu cần phân biệt cả không truyền, truyền null và truyền giá trị, chỉ một field kiểu bao cũng chưa đủ; phải có hợp đồng đầu vào thể hiện riêng các trạng thái đó.

### 11.4. Dùng lại entity đã đọc từ kho dữ liệu

Một entity lấy từ kho thường chứa nhiều giá trị hơn các tiêu chí người dùng chọn. Dùng thẳng entity đó làm probe có thể đưa cả ID, trạng thái và các thuộc tính khác vào so khớp.

Nên tạo probe mới từ bộ lọc và thiết lập matcher tương ứng. Nếu có tái sử dụng đối tượng, phải hiểu đầy đủ các thuộc tính sẽ tham gia điều kiện.

## 12. Lựa chọn cách triển khai

| Tình huống | Cách tiếp cận phù hợp |
| --- | --- |
| Thao tác chỉ tìm theo vài thuộc tính cố định | Dùng `withIgnorePaths` cho các thuộc tính không thuộc điều kiện |
| Domain thực sự chấp nhận trạng thái chưa có giá trị | Cân nhắc kiểu bao và matcher bỏ qua null |
| Domain cần nguyên thủy, màn hình có bộ lọc tùy chọn | DTO kiểu bao, chuyển sang probe và xây dựng danh sách bỏ qua |
| Cần tìm chính xác `false` hoặc `0` | Giữ nguyên giá trị và giữ thuộc tính trong matcher |
| Cần khoảng số, so sánh lớn hơn hoặc nhóm AND/OR phức tạp | Chọn cơ chế truy vấn phù hợp với module; QBE không phải công cụ tổng quát cho mọi điều kiện |

QBE thường phù hợp với tiêu chí bằng nhau và so khớp chuỗi theo khả năng module. Đừng dùng một giá trị nguyên thủy trên probe để ngầm diễn đạt điều kiện như `priority >= 0`; giá trị `0` trên probe không tự tạo toán tử lớn hơn hoặc bằng.

## 13. Bài tập tự kiểm tra

Với model `Customer` trong bài, hãy xác định điều kiện hiệu lực trước khi dự đoán kết quả truy vấn:

1. Probe chỉ đặt `country = "VN"`, matcher mặc định: những thuộc tính nào vẫn tạo điều kiện?
2. Matcher gọi `withIgnoreNullValues()`: `active = false` có bị loại không?
3. DTO nhận `active = false`, `priority = null`: bộ chuyển đổi cần giữ và bỏ qua những đường dẫn nào?
4. Domain đổi sang `Boolean active` nhưng constructor gán `true`: probe mới có bỏ qua `active` theo mặc định không?
5. Người dùng gửi `priority = 0`: vì sao không thể dùng điều kiện `priority > 0` để xác định bộ lọc có được truyền?

Gợi ý đáp án:

1. `country`, `active` và `priority` tham gia; `id` đang null được bỏ qua.
2. Không. `false` không phải null.
3. Giữ `active` để lọc `false`; bỏ qua `priority`. `country` tham gia nếu có giá trị.
4. Không. Giá trị hiện tại là `true`, không còn là null.
5. Vì `0` là một giá trị được truyền và có thể hợp lệ; chỉ kiểm tra dương sẽ làm mất tiêu chí đó.

Nguyên tắc áp dụng là giữ riêng hai thông tin: **người dùng có chọn tiêu chí hay không** và **giá trị họ muốn tìm là gì**. Kiểu nguyên thủy chỉ giữ được thông tin thứ hai; với QBE, matcher hoặc mô hình bộ lọc phải cung cấp thông tin còn lại.