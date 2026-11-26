# Bind theo tên, theo vị trí và annotation `@Param`

## Mục tiêu bài học

Một query method có thể nhận nhiều tham số Java, trong khi câu truy vấn dùng tên hoặc số thứ tự để đánh dấu chỗ cần điền giá trị. Parameter binding là bước liên kết hai phía này. Nếu liên kết sai, ứng dụng có thể báo lỗi hoặc trả về dữ liệu sai dù câu truy vấn vẫn hợp lệ.

Sau bài học, bạn có thể:

- Phân biệt binding của derived query với placeholder trong truy vấn khai báo.
- Đọc và viết truy vấn bind theo tên hoặc theo vị trí.
- Dùng đúng `org.springframework.data.repository.query.Param` và giải thích giới hạn của annotation này.
- Nhận diện khác biệt cú pháp giữa các module Spring Data.
- Xử lý có chủ đích các trường hợp `null`, collection, `LIKE`, phân trang và sắp xếp.

## 1. Binding nối giá trị Java với tham số truy vấn

Giả sử domain `Customer` có các thuộc tính:

```text
Customer
├── id: Long
├── tenantId: String
├── email: String
├── lastName: String
├── active: boolean
└── createdAt: Instant
```

Ứng dụng muốn tìm khách hàng thuộc một tenant và có email cụ thể:

```text
Lời gọi Java
    tenantId = "tenant-a"
    email    = "an@example.com"
            │
            ▼
Câu truy vấn có hai chỗ nhận giá trị
    tenantId = :tenantId
    email    = :email
            │
            ▼
Bộ máy truy vấn nhận câu truy vấn và các giá trị đã bind
```

Các giá trị phải đi vào đúng chỗ. Nếu `tenantId` và `email` đều có kiểu `String`, trình biên dịch không thể phát hiện việc đảo nhầm ý nghĩa của chúng.

Trong Spring Data, cần tách ba phần:

| Thành phần | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Chữ ký phương thức Java | `search(String tenantId, String email)` | Khai báo những đầu vào phương thức nhận |
| Biểu thức truy vấn | `c.tenantId = :tenantId` | Mô tả điều kiện và vị trí nhận giá trị |
| Metadata binding | `@Param("tenantId")` | Liên kết tham số Java với tên trong truy vấn, khi store hỗ trợ |

Spring Data Commons cung cấp abstraction và metadata về tham số repository. Việc đọc ngôn ngữ truy vấn, hiểu placeholder và đưa giá trị xuống backend do module lưu trữ cùng công nghệ truy cập dữ liệu tương ứng thực hiện.

Vì vậy, không có quy tắc chung rằng mọi repository Spring Data đều dùng cùng một ký hiệu placeholder hoặc cùng một số bắt đầu.

## 2. Derived query không phải truy vấn có placeholder viết tay

Với derived query, bạn mô tả điều kiện bằng tên phương thức:

```java
interface CustomerRepository extends Repository<Customer, Long> {

    List<Customer> findByTenantIdAndEmail(
            String tenantId, String email);
}
```

Ví dụ cần import `java.util.List` và `org.springframework.data.repository.Repository`, cùng một domain `Customer` đã được mapping theo store. Nó giả định store hỗ trợ derived query tương ứng.

Ở đây, bạn không viết `:tenantId`, `?1` hay `?0`. Store phân tích tên phương thức và ghép các giá trị bindable với các phần điều kiện theo hợp đồng của derived query.

Trong ví dụ, giá trị bindable đầu tiên phục vụ điều kiện `TenantId`; giá trị tiếp theo phục vụ `Email`. Đổi tên biến Java không tự đổi thứ tự điều kiện trong tên phương thức.

```java
// Chữ ký gây hiểu nhầm: tên biến không khớp vai trò theo thứ tự điều kiện.
List<Customer> findByTenantIdAndEmail(String email, String tenantId);
```

Đây không phải cách yêu cầu Spring Data ghép email trước rồi tự tìm lại tenant theo tên biến. Với dạng derived query này, bạn phải giữ thứ tự tham số phù hợp với thứ tự các phần điều kiện. Thêm `@Param` không biến nó thành một truy vấn khai báo có named parameter.

Khi cần kiểm soát rõ tên placeholder, hãy dùng một cơ chế declared query mà store hỗ trợ, thay vì dựa vào cách đặt tên biến của derived query.

## 3. Bind theo tên với `@Param`

### 3.1. Ví dụ riêng cho Spring Data JPA

```java
import java.util.List;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

interface JpaCustomerRepository extends Repository<Customer, Long> {

    @Query("""
        select c from Customer c
        where c.tenantId = :tenantId
          and c.email = :email
        """)
    List<Customer> search(
            @Param("tenantId") String tenantId,
            @Param("email") String email);
}
```

Đây là truy vấn JPQL, giả định entity có tên `Customer` và các thuộc tính `tenantId`, `email`. Ví dụ cần môi trường JPA được cấu hình đầy đủ; nó không phải truy vấn chung có thể đưa nguyên sang MongoDB.

Bảng ánh xạ cho lời gọi:

```java
repository.search("tenant-a", "an@example.com");
```

| Tham số Java | Metadata | Placeholder JPQL | Giá trị |
| --- | --- | --- | --- |
| `tenantId` | `@Param("tenantId")` | `:tenantId` | `"tenant-a"` |
| `email` | `@Param("email")` | `:email` | `"an@example.com"` |

Giá trị trong `@Param` không chứa dấu `:`. Dấu `:` thuộc cú pháp placeholder của JPQL; tên liên kết là `tenantId` hoặc `email`.

### 3.2. Tên annotation phải khớp tên placeholder

Ví dụ lỗi:

```java
@Query("select c from Customer c where c.email = :email")
List<Customer> search(@Param("mail") String email);
```

Câu truy vấn yêu cầu tên `email`, trong khi annotation cung cấp tên `mail`. Việc biến Java vẫn có tên `email` không làm cho annotation sai trở nên đúng.

Cách sửa là thống nhất tên:

```java
@Query("select c from Customer c where c.email = :email")
List<Customer> search(@Param("email") String email);
```

Hãy coi tên placeholder là một phần của hợp đồng phương thức và kiểm tra chính tả nhất quán, kể cả chữ hoa và chữ thường.

### 3.3. Một giá trị có thể xuất hiện ở nhiều vị trí trong truy vấn

```java
@Query("""
    select c from Customer c
    where c.tenantId = :tenantId
      and (c.email = :term or c.lastName = :term)
    """)
List<Customer> searchByEmailOrLastName(
        @Param("tenantId") String tenantId,
        @Param("term") String term);
```

Hai lần xuất hiện của `:term` nhận cùng một giá trị. Không cần khai báo hai tham số Java cho cùng một đầu vào chỉ vì placeholder được sử dụng hai lần.

Điều kiện tenant bao ngoài nhóm `Or`, nên cả nhánh email lẫn nhánh họ đều bị giới hạn trong cùng tenant. Binding đúng không thể thay thế việc viết đúng cấu trúc điều kiện.

## 4. Annotation `@Param` thực sự làm gì?

Package cần dùng cho tham số repository là:

```java
import org.springframework.data.repository.query.Param;
```

`@Param` cung cấp tên cho một tham số phương thức để cơ chế truy vấn có thể liên kết tên đó với named parameter, khi module lưu trữ và loại truy vấn hỗ trợ.

Nó không tự thực hiện các công việc sau:

- Tạo ra câu truy vấn khi chưa có một cơ chế query method phù hợp.
- Chuyển JPQL thành SQL hoặc đổi cú pháp MongoDB thành JPQL.
- Xác thực tenant, kiểm tra quyền hoặc kiểm tra định dạng email.
- Chọn tên bảng, tên cột, tên thuộc tính hoặc chiều sắp xếp từ một giá trị đầu vào.
- Biến `null` thành điều kiện tùy chọn hay tự quyết định cách xử lý collection rỗng.

Đặc biệt, đừng nhầm các annotation có tên gần giống:

| Annotation | Vai trò |
| --- | --- |
| `org.springframework.data.repository.query.Param` | Đặt tên cho tham số repository phục vụ binding |
| `org.springframework.web.bind.annotation.RequestParam` | Nhận tham số từ HTTP request ở tầng web |
| `org.springframework.web.bind.annotation.PathVariable` | Nhận giá trị từ đường dẫn HTTP |

Một tham số HTTP có tên `email` không tự tạo ra metadata binding cho tham số repository. Controller, service và repository là các hợp đồng khác nhau; giá trị phải được truyền qua các tầng có chủ đích.

## 5. Bind theo vị trí

### 5.1. JPA dùng các vị trí như `?1`, `?2`

Ví dụ riêng cho Spring Data JPA:

```java
@Query("""
    select c from Customer c
    where c.tenantId = ?1
      and c.email = ?2
    """)
List<Customer> search(String tenantId, String email);
```

Trong JPQL, positional parameter bắt đầu từ `1`:

```text
?1 ← giá trị bindable thứ nhất: tenantId
?2 ← giá trị bindable thứ hai: email
```

Không cần `@Param` để đặt tên cho các vị trí trên. Annotation đặt tên cũng không phải công cụ để hoán đổi ý nghĩa của `?1` và `?2`.

Nếu bạn đổi chữ ký thành:

```java
List<Customer> search(String email, String tenantId);
```

thì phải kiểm tra và cập nhật các vị trí trong câu truy vấn, đồng thời cập nhật nơi gọi. Nếu giữ nguyên câu truy vấn, giá trị email sẽ đi vào điều kiện tenant và ngược lại.

Một query method có thể tiếp tục biên dịch sau thay đổi sai này, vì hai tham số cùng kiểu `String`. Đây là rủi ro về ngữ nghĩa, không phải lỗi kiểu Java.

### 5.2. MongoDB dùng các placeholder như `?0`, `?1`

Ví dụ riêng cho Spring Data MongoDB:

```java
import java.util.List;

import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.repository.Repository;

interface MongoCustomerRepository extends Repository<Customer, Long> {

    @Query("{ 'tenantId': ?0, 'email': ?1 }")
    List<Customer> search(String tenantId, String email);
}
```

Trong cú pháp truy vấn này:

```text
?0 ← giá trị bindable thứ nhất: tenantId
?1 ← giá trị bindable thứ hai: email
```

Import `@Query` ở đây thuộc module MongoDB. Nó khác với `org.springframework.data.jpa.repository.Query` dù tên đơn giản của annotation giống nhau.

Không đưa quy tắc `?0` sang JPQL. Cũng không đổi các placeholder MongoDB thành `:tenantId` chỉ bằng cách thêm `@Param` rồi kỳ vọng cú pháp named parameter của JPA sẽ hoạt động.

### 5.3. Bảng đối chiếu phạm vi

| Ngữ cảnh | Cách biểu đạt đầu vào trong ví dụ | Điểm cần nhớ |
| --- | --- | --- |
| Derived query | Tên như `findByTenantIdAndEmail` | Điều kiện được suy diễn; không có placeholder viết tay |
| JPA JPQL, theo tên | `:tenantId`, `:email` | Có thể liên kết qua `@Param` |
| JPA JPQL, theo vị trí | `?1`, `?2` | Đánh số bắt đầu từ `1` |
| MongoDB `@Query` trong ví dụ | `?0`, `?1` | Đánh số bắt đầu từ `0` |
| Native SQL hoặc store khác | Phụ thuộc module, provider và loại truy vấn | Phải xác nhận đúng cú pháp và mức hỗ trợ |

Ngay trong JPA, không nên suy rộng mọi khả năng của named parameter trong JPQL sang native SQL trên mọi provider. Native query còn phụ thuộc provider và database; tính hỗ trợ không chỉ do Commons quyết định.

## 6. So sánh binding theo tên và theo vị trí

| Tiêu chí | Theo tên | Theo vị trí |
| --- | --- | --- |
| Liên kết chính | Tên placeholder và metadata tên tham số | Số thứ tự của tham số bindable |
| Khả năng đọc | Dễ thấy ý nghĩa với nhiều tham số | Ngắn với truy vấn ít tham số |
| Đổi thứ tự khai báo Java | Có thể giữ nguyên truy vấn nếu liên kết tên vẫn đúng | Phải rà soát lại các vị trí |
| Đổi tên placeholder | Phải đổi metadata liên kết tương ứng | Không có tên placeholder để đổi |
| Rủi ro thường gặp | Lệch tên, sai annotation, mất metadata tên | Đảo thứ tự, nhầm chỉ số bắt đầu |
| Khả năng áp dụng | Cần store và loại truy vấn hỗ trợ | Cú pháp và chỉ số cũng phụ thuộc store |

Với truy vấn nhiều tham số cùng kiểu, named binding thường làm ý định rõ hơn. Tuy vậy, nó chỉ bảo vệ mối liên kết giữa tham số repository và truy vấn. Nếu nơi gọi truyền nhầm hai giá trị `String`, `@Param` không thể nhận ra đó là email được đưa vào biến tenant.

Nên chọn một phong cách thống nhất trong cùng một truy vấn. Không trộn `:email` với `?1` để giải quyết sự nhầm lẫn; nhiều cơ chế truy vấn không cho phép trộn, và cách viết đó cũng làm hợp đồng khó kiểm tra hơn.

## 7. Khi nào có thể bỏ `@Param`?

Một số module, chẳng hạn Spring Data JPA, có thể liên kết named parameter bằng tên tham số Java khi metadata tên được giữ lại và cơ chế đó được hỗ trợ.

```java
@Query("""
    select c from Customer c
    where c.tenantId = :tenantId
      and c.email = :email
    """)
List<Customer> search(String tenantId, String email);
```

Để cách viết này có cơ sở, cần bảo đảm quá trình biên dịch lưu tên tham số, chẳng hạn sử dụng tùy chọn Java `-parameters`, và module đang dùng hỗ trợ phát hiện tên cho loại truy vấn đó.

Đừng dựa vào việc IDE hiển thị được tên biến để kết luận file bytecode triển khai cũng chứa metadata phù hợp. Cấu hình build ở máy cá nhân và môi trường triển khai có thể khác nhau.

Có hai lựa chọn rõ ràng:

1. Dùng `@Param` để ghi trực tiếp tên binding tại chữ ký repository.
2. Bỏ annotation khi nhóm phát triển đã quy định, duy trì và xác minh cơ chế lưu tên tham số trong build.

Khi dùng `@Param`, tên biến Java có thể đổi mà tên binding vẫn giữ nguyên:

```java
@Query("select c from Customer c where c.email = :email")
List<Customer> search(@Param("email") String normalizedEmail);
```

Placeholder vẫn là `:email`; giá trị đến từ biến `normalizedEmail`. Đây có thể là lựa chọn hợp lý khi muốn tên biến thể hiện dữ liệu đã được xử lý ở tầng gọi. Annotation không tự chuẩn hóa giá trị đó.

## 8. Tham số đặc biệt không phải giá trị trong điều kiện

`Pageable` và `Sort` là những abstraction của Commons dùng để mô tả phân trang và thứ tự. Chúng không phải các giá trị nghiệp vụ để bind vào một điều kiện như `email = ...`.

Ví dụ JPA với named parameter:

```java
@Query("""
    select c from Customer c
    where c.tenantId = :tenantId
      and c.active = true
    """)
Page<Customer> findActiveCustomers(
        @Param("tenantId") String tenantId,
        Pageable pageable);
```

Ví dụ cần import `Page` và `Pageable` từ `org.springframework.data.domain`. Chỉ `tenantId` xuất hiện như một named parameter. `Pageable` được cơ chế repository xử lý theo vai trò đặc biệt của nó.

Không thêm `@Param("pageable")` với mong muốn truyền nguyên đối tượng này vào SQL hoặc JPQL. Thay vào đó, đặt điều kiện trong truy vấn và để repository áp dụng cơ chế phân trang được store hỗ trợ.

Khi dùng positional binding, cần xét danh sách **tham số bindable**, không đếm mù mọi tham số Java bao gồm cả `Pageable` và `Sort`. Đặt các tham số đặc biệt ở cuối chữ ký giúp người đọc dễ phân biệt hai nhóm.

### 8.1. Truy vấn dữ liệu và truy vấn đếm phải nhất quán

Với một `Page`, store có thể cần thêm truy vấn đếm. Trong JPA, có thể khai báo rõ `countQuery` khi phù hợp:

```java
@Query(
    value = """
        select c from Customer c
        where c.tenantId = :tenantId
          and c.active = true
        """,
    countQuery = """
        select count(c) from Customer c
        where c.tenantId = :tenantId
          and c.active = true
        """
)
Page<Customer> findActiveCustomers(
        @Param("tenantId") String tenantId,
        Pageable pageable);
```

Các bộ lọc của dữ liệu trang và tổng số phải biểu đạt cùng phạm vi. Nếu truy vấn dữ liệu lọc tenant nhưng truy vấn đếm bỏ quên tenant, số tổng có thể sai và còn làm lộ thông tin về phạm vi dữ liệu khác.

Không cần khai báo `countQuery` thủ công cho mọi truy vấn đơn giản; ví dụ nhằm làm rõ trách nhiệm khi bạn chủ động cung cấp hai câu truy vấn. Chi phí và việc có cần thực hiện phép đếm còn tùy store và tình huống lấy trang.

## 9. Những giá trị cần quy ước riêng

### 9.1. `null` không tự có nghĩa là “bỏ qua bộ lọc”

Với declared query JPA:

```java
@Query("""
    select c from Customer c
    where c.tenantId = :tenantId
      and c.email = :email
    """)
List<Customer> search(
        @Param("tenantId") String tenantId,
        @Param("email") String email);
```

Truyền `null` cho email không tự biến điều kiện thành “mọi email”. Trong ngữ nghĩa truy vấn quan hệ, so sánh bằng với `null` không tương đương `IS NULL`.

Nếu yêu cầu là “email không có thì bỏ lọc email”, phải biểu đạt rõ:

```java
@Query("""
    select c from Customer c
    where c.tenantId = :tenantId
      and (:email is null or c.email = :email)
    """)
List<Customer> searchWithOptionalEmail(
        @Param("tenantId") String tenantId,
        @Param("email") String email);
```

Đây là một lựa chọn ngữ nghĩa cụ thể, không phải quy tắc tự động của `@Param`. Nó vẫn giữ điều kiện tenant bắt buộc. Cần đánh giá tính phù hợp và kế hoạch thực thi của biểu thức với database đang dùng.

Nếu yêu cầu là “tìm khách hàng có email bị thiếu”, điều kiện cần hướng đến `c.email is null`, là một yêu cầu khác. Derived query và các store khác có thể có quy tắc xử lý `null` riêng; không sao chép máy móc hành vi của declared JPQL sang mọi query method.

### 9.2. Collection nên được bind như collection

Ví dụ JPA:

```java
@Query("""
    select c from Customer c
    where c.tenantId = :tenantId
      and c.email in :emails
    """)
List<Customer> findByEmailSet(
        @Param("tenantId") String tenantId,
        @Param("emails") Collection<String> emails);
```

Ví dụ cần import `java.util.Collection`. Hãy truyền một collection giá trị, không tự nối email thành chuỗi phân cách bằng dấu phẩy để đưa vào một placeholder.

Với collection rỗng, hãy quyết định hợp đồng nghiệp vụ trước. Chẳng hạn, “tập email rỗng nghĩa là không có kết quả” có thể được xử lý ở tầng gọi bằng cách trả một danh sách rỗng. Đừng để collection rỗng vô tình mang nghĩa “bỏ bộ lọc và lấy mọi khách hàng”.

Cách mở rộng collection và hỗ trợ tập rỗng phụ thuộc module, provider và database. Binding không loại bỏ các giới hạn như số lượng tham số tối đa của backend.

### 9.3. `LIKE` vẫn có ngữ nghĩa wildcard

Bind giá trị vào một biểu thức `LIKE` không tự làm cho ký tự `%` hoặc `_` trở thành ký tự thường. Có hai yêu cầu khác nhau:

- Cho phép người gọi cung cấp pattern tìm kiếm.
- Tìm nguyên văn một đoạn văn bản có thể chứa ký tự wildcard.

Ví dụ JPA tìm theo pattern:

```java
@Query("""
    select c from Customer c
    where c.tenantId = :tenantId
      and c.lastName like :pattern escape '!'
    """)
List<Customer> searchLastName(
        @Param("tenantId") String tenantId,
        @Param("pattern") String pattern);
```

Nếu muốn tìm một đoạn văn bản theo nghĩa nguyên văn, có thể chuẩn bị pattern theo quy ước escape vừa khai báo:

```java
static String escapeLikeLiteral(String input) {
    return input.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
}

// keyword phải được xử lý null theo hợp đồng của tầng gọi.
String pattern = "%" + escapeLikeLiteral(keyword) + "%";
List<Customer> customers = repository.searchLastName(tenantId, pattern);
```

Đây là xử lý ngữ nghĩa pattern, tách biệt với việc bind tham số an toàn. Quy tắc phân biệt hoa thường và collation vẫn do hệ thống truy vấn thực tế quyết định.

## 10. Bind giá trị không phải chèn cấu trúc truy vấn

Một placeholder thông thường đại diện cho một giá trị, chẳng hạn email, mốc thời gian hoặc mã tenant. Nó không đại diện cho một đoạn cú pháp tùy ý.

Ví dụ sau không phải cách chọn thuộc tính để sắp xếp:

```java
// Không dùng cách này để yêu cầu sắp xếp theo thuộc tính từ đầu vào.
@Query("select c from Customer c order by :property")
List<Customer> sortByProperty(@Param("property") String property);
```

Ngay cả khi một provider chấp nhận biểu thức đó, `:property` vẫn là một giá trị được bind, không phải tên thuộc tính được thay thế vào cây truy vấn. Nó không có nghĩa là `order by c.email` khi truyền chuỗi `"email"`.

Khi store và loại truy vấn hỗ trợ, hãy dùng `Sort` hoặc `Pageable` cho thứ tự động. Ở biên nhận dữ liệu bên ngoài, có thể ánh xạ một tập lựa chọn hữu hạn sang thuộc tính đã biết:

```text
Lựa chọn giao diện   Thuộc tính domain
moi-nhat         →  createdAt
ho               →  lastName
```

Nếu cần thay đổi join, tập cột, toán tử hoặc cấu trúc điều kiện, hãy dùng API xây dựng truy vấn hay fragment tùy biến phù hợp với store. Không nối trực tiếp các đoạn đầu vào chưa được kiểm soát vào câu truy vấn.

### 10.1. Binding và an toàn dữ liệu

Với một câu truy vấn có cấu trúc cố định, bind giá trị giúp backend xử lý đầu vào như dữ liệu thay vì diễn giải nó thành một đoạn cú pháp truy vấn. Ví dụ, một chuỗi có dấu nháy không cần được nối trực tiếp vào JPQL.

Tuy vậy, binding không xác nhận người gọi được phép truy cập tenant đã truyền vào. Service vẫn phải xác định tenant từ ngữ cảnh đã được tin cậy hoặc kiểm tra quyền phù hợp. Nếu người gọi được tự do chọn tenant khác, câu truy vấn bind hoàn toàn đúng vẫn có thể trả dữ liệu không được phép.

Tương tự, binding không tự bảo đảm mọi nhánh `Or` đều có điều kiện tenant. Cấu trúc truy vấn và nguồn giá trị đều phải đúng.

## 11. Refactor chữ ký mà không làm sai liên kết

Giả sử truy vấn theo tên dùng hai tham số:

```java
@Query("""
    select c from Customer c
    where c.tenantId = :tenantId
      and c.email = :email
    """)
List<Customer> search(
        @Param("tenantId") String tenantId,
        @Param("email") String email);
```

Nếu thật sự cần đổi thứ tự khai báo:

```java
List<Customer> search(
        @Param("email") String email,
        @Param("tenantId") String tenantId);
```

thì liên kết trong câu truy vấn vẫn đúng nhờ tên. Nhưng nơi gọi phải đổi tương ứng:

```java
// Theo chữ ký mới: email trước, tenant sau.
repository.search("an@example.com", "tenant-a");
```

Vì cả hai tham số là `String`, một nơi gọi chưa được sửa vẫn có thể biên dịch. Named binding không bảo vệ bạn khỏi lỗi truyền đối số ở tầng Java.

Một quy trình refactor hợp lý là:

1. Xác định phương thức đang là derived query hay declared query.
2. Với declared query, xác định binding theo tên hay theo vị trí.
3. Cập nhật annotation hoặc chỉ số theo lựa chọn mới.
4. Cập nhật nơi gọi theo chữ ký Java mới.
5. Xác minh bằng dữ liệu có thể phân biệt việc đảo email và tenant.

Đối với API repository có quá nhiều tham số cùng kiểu, nên cân nhắc tổ chức lại yêu cầu truy vấn trong một implementation tùy biến hoặc API truy vấn động được store hỗ trợ. Chỉ bọc các giá trị vào một object không làm cho mọi `@Query` tự hiểu cách bind từng thuộc tính của object đó.

## 12. Chẩn đoán lỗi theo biểu hiện

| Biểu hiện | Khả năng cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy named parameter | Tên trong `@Param` lệch với truy vấn | Đối chiếu từng placeholder với metadata tham số |
| Named binding chỉ lỗi ở môi trường triển khai | Build không giữ metadata tên khi bỏ `@Param` | Kiểm tra tùy chọn biên dịch hoặc dùng annotation rõ ràng |
| Lỗi chỉ số tham số | Nhầm `?0` và `?1`, thiếu đối số hoặc sai thứ tự | Xác định module, ngôn ngữ truy vấn và tham số bindable |
| Truy vấn chạy nhưng không có kết quả | Hai tham số cùng kiểu bị đảo hoặc giá trị không đúng | Kiểm tra lời gọi Java và bảng ánh xạ binding |
| Truy vấn lọt dữ liệu ngoài tenant | Cấu trúc điều kiện hoặc nguồn tenant sai | Kiểm tra nhánh `Or` và ngữ cảnh xác định tenant |
| Truyền `null` không bỏ bộ lọc | Truy vấn chưa định nghĩa ngữ nghĩa tùy chọn | Viết rõ điều kiện hoặc tách cách xây dựng truy vấn |
| Collection rỗng gây lỗi | Backend hoặc provider không hỗ trợ dạng sinh ra | Quy định và xử lý tập rỗng trước khi gọi |
| Kết quả `LIKE` rộng hơn mong muốn | Đầu vào chứa wildcard có ý nghĩa | Phân biệt pattern với tìm nguyên văn và escape phù hợp |
| `Pageable` bị hiểu thành tham số dữ liệu | Chữ ký hoặc kỳ vọng binding sai | Giữ vai trò tham số đặc biệt, dùng API phân trang |
| Tổng số trang không khớp dữ liệu | `countQuery` khác bộ lọc hoặc binding | Đối chiếu điều kiện và tham số giữa hai truy vấn |

Nhiều lỗi được phát hiện khi repository hoặc truy vấn được chuẩn bị, nhưng không nên hứa rằng mọi lỗi binding đều xuất hiện ngay lúc khởi động. Cấu hình khởi tạo trì hoãn, loại truy vấn, provider và dữ liệu thực có thể khiến lỗi chỉ xuất hiện khi thực thi.

Khi xem log để chẩn đoán, cần quan sát cả cấu trúc truy vấn lẫn vai trò của giá trị, tránh chỉ kết luận rằng “câu truy vấn chạy được”. Các giá trị như email hoặc định danh tenant có thể là dữ liệu nhạy cảm; dùng dữ liệu kiểm thử để quan sát ánh xạ khi có thể.

## 13. Bài tập tự kiểm tra

### Bài 1: Tên biến hay tên annotation?

```java
@Query("select c from Customer c where c.email = :email")
List<Customer> search(@Param("mail") String email);
```

Binding này có đúng không?

**Gợi ý đáp án:** Không. Metadata đặt tên là `mail`, còn truy vấn yêu cầu `email`. Cần đổi `@Param("mail")` thành `@Param("email")`, hoặc đổi placeholder cho nhất quán. Tên biến Java không sửa được tên annotation đã khai báo sai.

### Bài 2: Hai kiểu đánh số

Một truy vấn JPA dùng `?1`, `?2`; một truy vấn MongoDB dùng `?0`, `?1`. Có nên chuẩn hóa cả hai về cùng chỉ số bắt đầu chỉ vì chúng cùng thuộc Spring Data không?

**Gợi ý đáp án:** Không. Chỉ số thuộc cú pháp và cơ chế binding của từng module. Commons không biến chúng thành một ngôn ngữ chung.

### Bài 3: Đổi thứ tự tham số

Một JPQL query dùng `:tenantId` và `:email`, mỗi tham số được gắn `@Param` đúng tên. Nếu đổi thứ tự khai báo Java mà vẫn giữ annotation đúng với từng giá trị, có cần đổi truy vấn không? Có cần đổi nơi gọi không?

**Gợi ý đáp án:** Truy vấn không cần đổi chỉ vì thứ tự mới; liên kết vẫn theo tên. Nơi gọi phải tuân theo thứ tự của chữ ký Java mới. Hai tham số cùng kiểu có thể bị truyền nhầm mà vẫn biên dịch.

### Bài 4: Tham số đặc biệt

```java
Page<Customer> search(
        @Param("tenantId") String tenantId,
        Pageable pageable);
```

Câu truy vấn có bắt buộc chứa `:pageable` không?

**Gợi ý đáp án:** Không. `Pageable` được repository xử lý theo vai trò phân trang; nó không phải một giá trị điều kiện thông thường. Ví dụ giả định store và loại truy vấn hỗ trợ hợp đồng này.

### Bài 5: Kiểm tra ánh xạ bằng dữ liệu

Bạn cần xác minh một truy vấn tìm email trong tenant. Hãy chọn dữ liệu sao cho có cùng email ở hai tenant, một email khác trong cùng tenant và một lời gọi không có kết quả.

**Gợi ý đáp án:** Kết quả phải phụ thuộc đồng thời vào tenant và email. Bộ dữ liệu đó có thể phát hiện thiếu điều kiện tenant, đảo tham số hoặc bind nhầm tên tốt hơn một ca duy nhất chứa đúng một khách hàng.

## Những điểm cần nhớ

- Trước khi đọc placeholder, xác định đúng store, import `@Query` và loại truy vấn.
- Derived query ghép giá trị theo cấu trúc điều kiện; named binding của declared query là một cơ chế khác.
- `@Param` đặt tên binding, không tự tạo truy vấn hay đổi cấu trúc truy vấn.
- Với JPQL, các ví dụ positional dùng `?1`; với MongoDB `@Query`, các ví dụ dùng `?0` cho giá trị đầu tiên.
- `Pageable` và `Sort` là tham số đặc biệt; `null`, collection rỗng và wildcard cần hợp đồng riêng.
- Binding đúng cần đi cùng logic điều kiện đúng, nguồn tenant đáng tin cậy và lời gọi Java truyền đúng ý nghĩa của từng đối số.
