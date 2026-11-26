# Sắp xếp có kiểu với TypedSort hoặc TypedPropertyPath theo phiên bản

## Mục tiêu bài học

`Sort.by("lastName")` ngắn gọn nhưng tên thuộc tính nằm trong một chuỗi. Nếu đổi tên getter hoặc gõ sai tên, trình biên dịch Java không trực tiếp phát hiện mối liên hệ giữa chuỗi đó và domain. Sắp xếp có kiểu giúp biểu đạt thuộc tính bằng API gắn với kiểu domain và, trong những API phù hợp, bằng method reference.

Sau bài học, bạn có thể:

- Tạo thứ tự bằng `Sort.TypedSort<T>` ở dòng API hỗ trợ.
- Kết hợp nhiều thuộc tính và hướng mà vẫn giữ đúng thứ tự ưu tiên.
- Phân biệt mức an toàn tại thời điểm biên dịch với khả năng truy vấn thực tế của store.
- Nhận diện các ràng buộc do cơ chế ghi nhận getter bằng proxy của TypedSort.
- Chọn đúng hướng API khi dự án sử dụng `TypedSort` hoặc một API đường dẫn có kiểu như `TypedPropertyPath` theo phiên bản.

Bài học cung cấp ví dụ Java cụ thể với TypedSort. Với TypedPropertyPath, cần dùng đúng điểm tạo đường dẫn và cách tích hợp với Sort mà phiên bản dependency thực tế công bố; không suy ra chữ ký Java chỉ từ tên lớp.

## 1. Vì sao chuỗi tên thuộc tính có giới hạn?

Giả sử domain khách hàng có các thuộc tính:

```text
Customer
├── id: Long
├── tenantId: String
├── firstName: String
├── lastName: String
├── createdAt: Instant
├── active: boolean
└── address: Address
    └── city: String
```

Một thứ tự dùng chuỗi:

```java
Sort sort = Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("firstName"),
        Sort.Order.asc("id")
);
```

Java chỉ biết rằng các đối số là chuỗi. Những giá trị như `"lastNmae"` vẫn là chuỗi hợp lệ với trình biên dịch, dù không phải thuộc tính đúng.

Một IDE có thể hỗ trợ refactor hoặc kiểm tra chuỗi trong vài ngữ cảnh, nhưng đó không phải bảo đảm của hệ kiểu Java. Nếu tên getter đổi mà chuỗi chưa được cập nhật, lỗi có thể chỉ xuất hiện lúc store phân tích hoặc thực thi truy vấn.

Sắp xếp có kiểu giảm một phần rủi ro đó bằng cách liên kết biểu thức chọn thuộc tính với domain. Nó vẫn phải tạo ra một yêu cầu sort mà module lưu trữ hiểu được.

## 2. Chọn API theo dependency đang dùng

Không nên trộn ví dụ từ nhiều dòng tài liệu vào cùng một đoạn code. Cùng mục tiêu chọn thuộc tính có kiểu có thể được biểu đạt bằng các API khác nhau theo phiên bản.

| Dấu hiệu trong API của dự án | Hướng sử dụng |
| --- | --- |
| Có `Sort.sort(Class<T>)` và `Sort.TypedSort<T>` | Dùng TypedSort theo ví dụ trong bài |
| Phiên bản cung cấp `TypedPropertyPath` cùng cách tích hợp sắp xếp | Tạo đường dẫn có kiểu và chuyển sang Order/Sort bằng đúng API của dòng đó |
| Chỉ có overload Sort dựa trên tên thuộc tính đáp ứng môi trường hiện tại | Giữ Sort dùng chuỗi với chính sách tập trung và kiểm tra mapping phù hợp |
| Dự án đã có tích hợp metamodel như Querydsl | Xem API sắp xếp của tích hợp đó và mức hỗ trợ của store |

Tên lớp mới trong một tài liệu không có nghĩa mọi ứng dụng Spring Data đã có lớp đó. Cần xét phiên bản `spring-data-commons`, module store, bộ dependency được quản lý và mức Java của dự án.

Khả năng tạo một đường dẫn có kiểu cũng chưa đủ: phải có cách hợp lệ để dùng đường dẫn đó trong yêu cầu sắp xếp của phiên bản tương ứng. Không tự chuyển đường dẫn bằng `toString()` rồi coi chuỗi debug là hợp đồng tên thuộc tính.

### Phân biệt hai loại tương thích

- **Tương thích API:** đoạn code có dùng đúng lớp, package, overload và generic mà dependency cung cấp không?
- **Tương thích thực thi:** store và môi trường chạy có hỗ trợ đường dẫn, kiểu query và cơ chế xây dựng sort đó không?

Có thể vượt qua loại thứ nhất nhưng vẫn thất bại ở loại thứ hai, chẳng hạn getter có tồn tại nhưng thuộc tính không được mapping.

## 3. Tạo TypedSort từ kiểu domain

Với dòng API cung cấp TypedSort:

```java
import org.springframework.data.domain.Sort;

Sort.TypedSort<Customer> customer = Sort.sort(Customer.class);

Sort sort = customer.by(Customer::getLastName).ascending();
```

Ví dụ giả định `Customer` có getter JavaBean công khai tương ứng và kiểu có thể được cơ chế TypedSort ghi nhận bằng proxy. Mapping persistence được cấu hình riêng theo store.

Ý nghĩa:

1. `Sort.sort(Customer.class)` bắt đầu từ kiểu domain `Customer`.
2. `by(Customer::getLastName)` chọn accessor của thuộc tính cần sắp xếp.
3. `ascending()` tạo yêu cầu thứ tự tăng dần.

Với getter JavaBean thông thường, thuộc tính được biểu đạt là `lastName`. Không cần có một đối tượng Customer được đọc từ database để viết biểu thức này.

### Method reference giúp được gì?

Trình biên dịch có thể phát hiện nhiều lỗi tại nơi khai báo:

- Getter được tham chiếu không tồn tại.
- Method reference không phù hợp với kiểu đầu vào mà API yêu cầu.
- Việc đổi tên hoặc xóa getter làm biểu thức hiện tại không còn hợp lệ.

Những bảo đảm này hữu ích khi refactor. Tuy vậy, trình biên dịch không kiểm tra rằng `lastName` đã được ánh xạ vào một cột hay trường mà store có thể sắp xếp.

## 4. Nhiều thuộc tính và hướng khác nhau

Yêu cầu:

```text
lastName ASC, firstName ASC, id ASC
```

Có thể viết:

```java
Sort.TypedSort<Customer> customer = Sort.sort(Customer.class);

Sort byName = customer.by(Customer::getLastName).ascending()
        .and(customer.by(Customer::getFirstName).ascending())
        .and(customer.by(Customer::getId).ascending());
```

Yêu cầu khác:

```text
createdAt DESC, id DESC
```

```java
Sort newestFirst = customer.by(Customer::getCreatedAt).descending()
        .and(customer.by(Customer::getId).descending());
```

Kiểu của accessor không quyết định hướng. Bạn vẫn chọn `ascending()` hoặc `descending()` một cách tường minh theo yêu cầu nghiệp vụ.

### Thứ tự ưu tiên vẫn từ trái sang phải

Trong `byName`, chỉ khi `lastName` bằng nhau thì `firstName` mới được xét; nếu cả hai bằng nhau, `id` phân biệt các khách hàng.

Method reference không thay đổi nguyên tắc nhiều tiêu chí của `Sort`. `.and()` vẫn nối tiêu chí sau những tiêu chí hiện có và không tự ghi đè theo tên thuộc tính.

```java
Sort a = customer.by(Customer::getLastName).ascending();
Sort b = customer.by(Customer::getCreatedAt).descending();

Sort nameFirst = a.and(b);
Sort timeFirst = b.and(a);
```

Hai thứ tự có ưu tiên khác nhau. Sắp xếp có kiểu không làm phép kết hợp trở thành giao hoán.

### Cần giữ kết quả trả về

```java
Sort sort = customer.by(Customer::getLastName).ascending();

sort = sort.and(customer.by(Customer::getId).ascending());
```

Việc bỏ qua kết quả của `.and()` không bổ sung tiêu chí vào biến `sort`. Tính bất biến của giá trị Sort vẫn áp dụng khi nó được xây dựng từ TypedSort.

## 5. Đường dẫn thuộc tính lồng nhau

Với các dòng TypedSort hỗ trợ việc nối các bước chọn accessor, có thể diễn đạt một đường dẫn lồng nhau theo kiểu:

```java
Sort.TypedSort<Customer> customer = Sort.sort(Customer.class);

Sort byCity = customer
        .by(Customer::getAddress)
        .by(Address::getCity)
        .ascending()
        .and(customer.by(Customer::getId).ascending());
```

Ví dụ giả định `Customer.getAddress()` trả `Address`, `Address.getCity()` trả `String`, và các kiểu cần thiết đều phù hợp với cơ chế ghi nhận của API.

Điểm hữu ích là bước tiếp theo được gắn với kiểu trả về của bước trước. Nếu accessor địa chỉ đổi sang một kiểu khác không có `getCity`, biểu thức cần được cập nhật.

Tuy vậy, đường dẫn Java có thể biểu đạt được không có nghĩa backend hỗ trợ nó trong mọi query:

- JPA có thể cần điều hướng quan hệ và quy tắc join tương ứng.
- Document store có cách điều hướng trường lồng nhau riêng.
- Đường dẫn đi qua collection có thể tạo ra yêu cầu khác với đường dẫn đơn trị.
- Giá trị trung gian bị thiếu/null có thể ảnh hưởng kết quả và null ordering.

Không tự diễn giải một đường dẫn lồng nhau thành yêu cầu inner join, outer join hoặc một chính sách đặt null cụ thể chỉ từ chuỗi method reference.

Nếu một phiên bản có chữ ký chọn đường dẫn khác, cần dùng đúng API của phiên bản đó. Không ghép một bước chọn accessor của TypedSort với một bước của TypedPropertyPath mà chưa có hợp đồng tích hợp rõ ràng.

## 6. Cơ chế proxy của TypedSort và các giới hạn thực tế

TypedSort sử dụng cơ chế ghi nhận lời gọi thuộc tính bằng runtime proxy; trong các môi trường thông thường cơ chế này có thể dựa vào proxy lớp như CGLIB.

Method reference trong ví dụ dùng để ghi nhận accessor, không phải để lấy một giá trị thật từ một khách hàng đang tồn tại. Đây là lý do chỉ nhìn việc code biên dịch được chưa đủ để biết việc tạo sort sẽ thành công ở runtime.

### 6.1. Kiểu hoặc method không phù hợp với proxy

Các lớp final, record và method final có thể gặp hạn chế với cơ chế proxy lớp và chặn lời gọi tương ứng. Không mặc định rằng một domain có accessor hợp lệ với Java thì cũng dùng được với mọi cách ghi nhận của TypedSort.

Với ví dụ TypedSort trong bài, nên dùng domain/getter phù hợp với cơ chế này và kiểm tra việc tạo sort trong môi trường thực thi mục tiêu. Không nên bỏ đặc tính final hoặc đổi toàn bộ mô hình domain chỉ để né một vấn đề mà một hướng xây dựng sort khác có thể giải quyết rõ hơn.

### 6.2. Method reference nên chỉ biểu đạt accessor

Ví dụ cần tránh:

```java
Sort sort = customer
        .by(c -> c.getLastName().toLowerCase())
        .ascending();
```

Biểu thức trên trộn chọn thuộc tính với xử lý chuỗi trên một giá trị mà cơ chế ghi nhận có thể không cung cấp như một đối tượng thật. Nó cũng không tự tạo yêu cầu `lower(lastName)` ở database.

Nếu cần so sánh không phân biệt hoa thường hoặc một biểu thức backend, hãy dùng cơ chế được store hỗ trợ và một hợp đồng truy vấn phù hợp. Một lambda Java có thể thực hiện tính toán không có nghĩa tính toán đó được dịch thành cú pháp truy vấn.

### 6.3. Getter tính toán chưa chắc là thuộc tính persistent

Một getter như `getDisplayLabel()` có thể chỉ nối họ và tên trong Java. Việc tham chiếu getter đó có thể hợp lệ với trình biên dịch, nhưng store không nhất thiết có một thuộc tính queryable tương ứng.

TypedSort không tự dịch nội dung getter thành phép nối chuỗi, không tự tạo cột tính toán và không quyết định index cho kết quả tính toán ấy.

### 6.4. AOT và native image

Runtime proxy có thể tạo thêm ràng buộc khi ứng dụng dùng AOT hoặc native image. Không kết luận rằng TypedSort luôn hoạt động hoặc luôn không hoạt động trong mọi cấu hình native; cần xác minh đúng dòng API, cơ chế proxy và môi trường build/run đang dùng.

Khi chọn một API khác như TypedPropertyPath trong dòng có hỗ trợ, cần đánh giá cơ chế thực tế của API đó. Không tự áp toàn bộ hạn chế proxy của TypedSort cho một API chỉ vì cả hai đều chọn thuộc tính có kiểu.

## 7. Cách tiếp cận khi phiên bản dùng TypedPropertyPath

Một API đường dẫn có kiểu như TypedPropertyPath tách vấn đề chọn thuộc tính thành một biểu diễn đường dẫn có thông tin kiểu. Để dùng cho sort, cần quan tâm cả kiểu gốc, đường dẫn được chọn và cách chuyển thành tiêu chí có hướng.

Luồng khái niệm:

```text
Kiểu domain
    ↓ chọn thuộc tính hoặc nối đường dẫn theo API có hỗ trợ
Đường dẫn thuộc tính có kiểu
    ↓ chọn hướng qua cơ chế tích hợp của phiên bản
Order hoặc Sort
    ↓ kết hợp các tiêu chí theo ưu tiên
Yêu cầu sắp xếp đưa vào repository
```

Đây là mô tả các bước, không phải một bộ tên factory Java dùng chung cho mọi phiên bản.

Khi áp dụng một ví dụ TypedPropertyPath, hãy làm rõ:

| Thành phần | Điều cần đối chiếu |
| --- | --- |
| Package và kiểu generic | Đúng với artifact đang có, không chỉ cùng tên đơn giản |
| Cách khởi tạo | Factory/entry point thật sự được phiên bản công bố |
| Chọn thuộc tính | Accessor, metamodel hoặc hình thức mà API đó hỗ trợ |
| Đường dẫn lồng nhau | Cách giữ thông tin kiểu giữa các bước |
| Tích hợp Sort | Overload/factory tạo Order hoặc Sort phù hợp |
| Giới hạn thực thi | Những ràng buộc được API và store quy định |

Nếu dependency chưa có API này, giữ một ví dụ TypedSort tương thích hoặc một cách xây dựng Sort khác đã được dự án hỗ trợ. Không thêm một đoạn code có tên lớp đúng nhưng factory suy đoán, vì người đọc sẽ không thể biên dịch nó.

Một lợi ích chung của hướng đường dẫn có kiểu là tập trung metadata thuộc tính để tái sử dụng. Tuy nhiên, không tự suy ra rằng một đường dẫn hợp lệ cũng dùng được cho mọi thao tác query, projection, update hay sort. Mỗi điểm tích hợp có thể có mức hỗ trợ riêng.

## 8. Kiểu trả về cuối cùng vẫn cần được dùng đúng domain

Một chi tiết quan trọng trong TypedSort là kết quả được truyền cho repository thường là `Sort`, không phải một kiểu kết quả vẫn mang generic `Customer` ở chữ ký repository.

```java
Sort.TypedSort<Customer> customer = Sort.sort(Customer.class);
Sort customerSort = customer.by(Customer::getLastName).ascending();
```

Khi đã nhận `Sort`, một phương thức repository khác nhận tham số `Sort` vẫn có thể chấp nhận đối tượng đó ở mức kiểu Java. Trình biên dịch không tự biết bạn đang truyền sort của Customer cho một domain khác.

Vì vậy, sắp xếp có kiểu bảo vệ tốt hơn tại điểm xây dựng, nhưng không bảo đảm mọi bước sử dụng về sau đều gắn chặt với cùng domain.

Một cách tổ chức rõ ràng là tập trung factory sắp xếp trong một policy của đúng domain và chỉ cung cấp các lựa chọn nghiệp vụ cần thiết.

### Ví dụ policy có lựa chọn hữu hạn

```java
import java.util.Objects;

import org.springframework.data.domain.Sort;

enum CustomerOrder {
    NAME_ASC,
    NEWEST_FIRST
}

final class CustomerSorts {

    private CustomerSorts() {
    }

    static Sort forOrder(CustomerOrder order) {
        Objects.requireNonNull(order, "order");

        Sort.TypedSort<Customer> customer = Sort.sort(Customer.class);

        switch (order) {
            case NAME_ASC:
                return customer.by(Customer::getLastName).ascending()
                        .and(customer.by(Customer::getFirstName).ascending())
                        .and(customer.by(Customer::getId).ascending());

            case NEWEST_FIRST:
                return customer.by(Customer::getCreatedAt).descending()
                        .and(customer.by(Customer::getId).descending());

            default:
                throw new IllegalArgumentException(
                        "Lựa chọn sắp xếp chưa được hỗ trợ");
        }
    }
}
```

Policy cho người gọi một tập lựa chọn rõ ràng, gắn tên lựa chọn với thứ tự cụ thể và giữ khóa phụ ở một nơi. Việc chuyển một tham số HTTP sang `CustomerOrder` vẫn cần được xử lý tại biên API.

Nếu domain hoặc môi trường không phù hợp với TypedSort, có thể thay implementation trong policy bằng cách xây dựng Sort khác được hỗ trợ mà vẫn giữ nguyên hợp đồng các lựa chọn này.

## 9. Dùng với repository, phân trang và phạm vi dữ liệu

Repository minh họa:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.Repository;

interface CustomerRepository extends Repository<Customer, Long> {

    List<Customer> findByTenantIdAndActiveTrue(
            String tenantId, Sort sort);

    Page<Customer> findByTenantIdAndActiveTrue(
            String tenantId, Pageable pageable);
}
```

Lấy danh sách:

```java
Sort sort = CustomerSorts.forOrder(CustomerOrder.NAME_ASC);

List<Customer> customers = repository.findByTenantIdAndActiveTrue(
        tenantId, sort);
```

Lấy trang:

```java
import org.springframework.data.domain.PageRequest;

Sort sort = CustomerSorts.forOrder(CustomerOrder.NEWEST_FIRST);
PageRequest pageable = PageRequest.of(0, 20, sort);

Page<Customer> page = repository.findByTenantIdAndActiveTrue(
        tenantId, pageable);
```

Ví dụ cần store hỗ trợ derived query, Sort và kiểu trả về tương ứng. Domain và kết nối được cấu hình riêng.

Khóa phụ `id` giúp phân biệt các khách hàng có cùng tên hoặc cùng thời điểm tạo, nếu id duy nhất trong phạm vi kết quả. Nó không tự tạo snapshot xuyên nhiều request và không ngăn dữ liệu thay đổi giữa các lần đọc trang.

Điều kiện tenant và trạng thái đến từ query method. Sắp xếp có kiểu không thay thế điều kiện phân quyền, không tự lọc dữ liệu và không xác định tenant mà người gọi được phép truy cập.

## 10. Những gì hệ kiểu chưa bảo đảm

| Điều có thể được hỗ trợ tại lúc xây dựng | Điều vẫn phải kiểm tra riêng |
| --- | --- |
| Accessor tồn tại trên kiểu Java | Thuộc tính có được mapping cho store không |
| Method reference phù hợp với kiểu gốc | Sort có được dùng cho đúng repository về sau không |
| Bước điều hướng phù hợp với kiểu trả về | Backend có hỗ trợ đường dẫn lồng nhau đó không |
| Refactor getter có thể làm lỗi lộ sớm | Cột, field, alias hoặc query khai báo có còn phù hợp không |
| Tạo tiêu chí từ accessor | Runtime proxy và native image có hoạt động trong môi trường đích không |
| Chọn hướng rõ ràng | Collation, null ordering và hiệu năng có đúng yêu cầu không |

Sắp xếp có kiểu cũng không tự tạo index. Một thứ tự hợp lệ có thể vẫn cần sort tốn tài nguyên nếu không có đường truy cập dữ liệu phù hợp. Cần xem điều kiện lọc, độ chọn lọc và thứ tự ưu tiên cùng nhau trên backend.

Các thay đổi mapping có thể không làm method reference lỗi biên dịch nhưng vẫn đổi cách truy vấn thực thi. Ví dụ, chuyển một thuộc tính sang dạng tính toán chỉ có trong Java cần được xem lại tại policy sort và query tương ứng.

## 11. Cách xác minh hợp đồng sắp xếp có kiểu

Có ba nhóm việc cần phân biệt:

1. **Biên dịch:** method reference và chữ ký API phù hợp với dependency.
2. **Tạo Sort:** cơ chế ghi nhận đường dẫn hoạt động, không vướng giới hạn proxy hoặc API.
3. **Thực thi query:** store hiểu các thuộc tính và trả dữ liệu đúng thứ tự.

Một kiểm tra ở nhóm thứ nhất không thay thế hai nhóm sau.

Có thể quan sát metadata Sort bằng cách duyệt các tiêu chí:

```java
Sort sort = CustomerSorts.forOrder(CustomerOrder.NAME_ASC);

for (Sort.Order order : sort) {
    System.out.println(order.getProperty() + " " + order.getDirection());
}
```

Với getter JavaBean như trong ví dụ, thứ tự mong đợi là:

```text
lastName ASC
firstName ASC
id ASC
```

Đối với hành vi query, dữ liệu nên có các khách hàng cùng họ, cùng cả họ lẫn tên, cùng thời điểm tạo và nằm sát biên trang. Khi dùng đường dẫn lồng nhau, cần có dữ liệu phù hợp với chính sách null/thiếu liên kết của store.

Nếu chạy native image hoặc một cấu hình AOT khác môi trường JVM thông thường, việc tạo và sử dụng sort cần được xác minh tại chính môi trường đó.

## 12. Bài tập tự kiểm tra

### Bài 1: Refactor thuộc tính

Nếu `Customer::getLastName` bị đổi tên nhưng code sort chưa cập nhật, lợi ích của TypedSort là gì so với chuỗi `"lastName"`?

**Gợi ý đáp án:** Method reference cũ không còn hợp lệ và có thể làm lỗi lộ ở lúc biên dịch. Chuỗi vẫn là một đối số Java hợp lệ, dù không còn khớp domain.

### Bài 2: Getter tính toán

Một getter `getFullName()` chỉ nối firstName và lastName trong Java. Có thể tự kết luận TypedSort sẽ dịch nội dung getter thành phép nối chuỗi ở database không?

**Gợi ý đáp án:** Không. Chọn accessor không có nghĩa dịch thân getter thành biểu thức truy vấn. Cần một thuộc tính hoặc cơ chế sort được store hỗ trợ.

### Bài 3: Domain final

Một record có accessor hợp lệ với Java. Điều đó có đủ bảo đảm cơ chế runtime proxy của mọi dòng TypedSort sẽ hoạt động không?

**Gợi ý đáp án:** Không. Cần xem cơ chế ghi nhận và giới hạn proxy của phiên bản. Có thể cần một API chọn đường dẫn khác hoặc một policy Sort tương thích với môi trường.

### Bài 4: Sort dùng nhầm nơi

Sau khi tạo `Sort` từ Customer, Java có tự ngăn bạn truyền nó vào repository của domain khác nhận tham số `Sort` không?

**Gợi ý đáp án:** Không phải trong chữ ký Sort thông thường. Vì kiểu cuối là Sort, cần tổ chức policy và cách sử dụng theo domain để tránh dùng nhầm.

### Bài 5: Hai dòng API

Tài liệu của một dòng mới dùng TypedPropertyPath nhưng dependency của dự án chỉ có TypedSort. Có nên tự đoán factory của TypedPropertyPath và thêm import để thử không?

**Gợi ý đáp án:** Không. Chọn API thực sự có trong bộ dependency, hoặc thực hiện một thay đổi phiên bản có chủ đích và tương thích. Không trộn chữ ký của các dòng tài liệu.

### Bài 6: Khóa phụ

TypedSort đã chọn `createdAt DESC`. Có tự bảo đảm thứ tự giữa hai khách hàng có cùng thời điểm không?

**Gợi ý đáp án:** Không. Cần thêm khóa phụ đủ phân biệt theo yêu cầu, chẳng hạn id trong phạm vi mà nó duy nhất. Cách tạo có kiểu không tự bổ sung tiêu chí.

## Những điểm cần nhớ

- Sắp xếp có kiểu giúp liên kết khai báo thuộc tính với domain, nhưng store vẫn quyết định khả năng thực thi.
- Với TypedSort, bắt đầu từ `Sort.sort(Domain.class)`, chọn accessor và ghép các tiêu chí theo đúng ưu tiên.
- Cơ chế runtime proxy tạo ra những giới hạn cần xem xét với kiểu final, getter, AOT và native image.
- TypedPropertyPath phải được dùng theo API và điểm tích hợp Sort của đúng phiên bản, không theo một chữ ký suy đoán.
- Kết quả Sort, mapping, khóa phụ, phạm vi tenant và index vẫn cần hợp đồng rõ ràng như khi sắp xếp bằng chuỗi.
