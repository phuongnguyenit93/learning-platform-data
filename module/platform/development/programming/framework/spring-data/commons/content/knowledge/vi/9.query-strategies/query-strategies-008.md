# Thời điểm phát hiện phương thức không hợp lệ hoặc thiếu truy vấn

Một ứng dụng biên dịch thành công vẫn có thể không khởi động được vì tên phương thức repository tham chiếu thuộc tính không tồn tại. Ngược lại, ứng dụng khởi động thành công vẫn có thể gặp lỗi khi lần đầu chạy SQL, hoặc khi đăng ký nhận kết quả reactive. Hai hiện tượng này không mâu thuẫn: mỗi tầng chỉ kiểm tra được những điều kiện mà nó có đủ thông tin để xác nhận.

Trong chương **Chiến lược truy vấn** của **SPRING_DATA_COMMONS**, bài này giúp xác định **lỗi nào được phát hiện ở giai đoạn nào**, giải thích ảnh hưởng của query lookup strategy, và chọn kiểm tra phù hợp để không nhầm “context đã chạy” với “truy vấn đã đúng”. Phạm vi gồm các abstraction repository dùng chung; những cơ chế riêng như JPQL và bootstrap mode được chỉ rõ là ví dụ Spring Data JPA.

## 1. Không có một thời điểm phát hiện lỗi chung cho mọi truy vấn

Cần phân biệt ít nhất năm mốc:

| Mốc | Việc có thể được kiểm tra | Điều mốc này chưa chứng minh |
| --- | --- | --- |
| Biên dịch Java | Cú pháp Java, kiểu dữ liệu trong chữ ký, import và lời gọi phương thức | Tên derived query có trỏ đến thuộc tính hợp lệ hay không; chuỗi truy vấn có đúng ngữ nghĩa hay không |
| Khám phá và đăng ký repository | Package được quét, interface nào tham gia cấu hình, module và hạ tầng tương ứng | Mọi repository đã được khởi tạo đầy đủ hoặc mọi truy vấn đã chạy |
| Khởi tạo repository và phân giải truy vấn | Metadata phương thức, phân tích tên, tìm khai báo, một số bước tạo và kiểm tra đối tượng truy vấn | Cơ sở dữ liệu sẽ chấp nhận mọi câu lệnh; dữ liệu trả về luôn phù hợp |
| Gọi phương thức và thực thi truy vấn | Binding tham số thực tế, kết nối, cú pháp được kho dữ liệu xử lý, quyền truy cập | Toàn bộ kết quả đã được đọc và chuyển đổi thành công |
| Đọc hết kết quả hoặc tiêu thụ publisher/stream | Chuyển đổi dữ liệu, đọc các phần tiếp theo, lỗi khi thực thi trì hoãn | Kết quả đã thỏa mọi quy tắc nghiệp vụ nếu chưa có kiểm tra hành vi |

Đây là các mốc khái niệm. Một module có thể gộp nhiều bước; một provider có thể hoãn một phần kiểm tra. Việc named query của JPA bị lỗi khi tạo `EntityManagerFactory`, chẳng hạn, có thể xảy ra trước lúc Spring Data phân giải phương thức repository liên quan.

Vì vậy, câu trả lời đúng không phải “repository sai luôn lỗi lúc startup” hoặc “chỉ gọi mới biết sai”. Cần biết **module nào**, **loại truy vấn nào**, **repository đã thật sự khởi tạo chưa** và **kết quả đã được thực thi, tiêu thụ đến đâu**.

## 2. Vì sao Java compiler không bắt được tên derived query sai?

Giả sử mô hình domain `PurchaseOrder` có các thuộc tính:

| Thuộc tính Java | Kiểu | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh |
| `status` | `OrderStatus` | Trạng thái đơn hàng |
| `createdAt` | `Instant` | Thời điểm tạo |
| `customerEmail` | `String` | Email khách hàng |

Ví dụ interface sau **cố ý đặt sai tên thuộc tính**:

```java
import java.util.List;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatuz(OrderStatus status);
}
```

`findByStatuz` vẫn là tên phương thức Java hợp lệ. Compiler không biết quy ước “phần sau `By` phải trỏ tới một thuộc tính domain”, nên không tự đối chiếu `Statuz` với `status`.

Khi Spring Data thực hiện suy diễn truy vấn, nó mới phân tích tên và thử giải quyết đường dẫn thuộc tính. Với domain không có `statuz`, bước này thường thất bại bằng lỗi phân giải thuộc tính, có thể xuất hiện trong cause chain dưới dạng `PropertyReferenceException`.

Cách sửa trong ví dụ là:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);
```

Không đổi thành tên cột SQL như `findByOrderStatus` chỉ vì trong cơ sở dữ liệu cột được đặt tên `order_status`. Tên derived query dựa trên thuộc tính Java được mô hình ánh xạ nhận diện, không dựa trực tiếp trên tên cột vật lý.

### Những thay đổi dễ làm xuất hiện lỗi kiểu này

- Đổi tên thuộc tính domain nhưng quên đổi các phương thức suy diễn liên quan.
- Viết sai đường dẫn thuộc tính lồng nhau.
- Dùng keyword mà module lưu trữ không hỗ trợ cho trường hợp đó.
- Dùng một toán tử với số lượng hoặc kiểu tham số không phù hợp.
- Tưởng tên nghiệp vụ tự do như `findOrdersForManualReview` sẽ tự trở thành điều kiện lọc.

Không phải mọi lỗi trong danh sách đều tạo ra cùng một exception hay cùng một thời điểm phát hiện. Điểm chung là compiler Java không phải bộ kiểm tra đầy đủ của hợp đồng truy vấn Spring Data.

## 3. Khởi tạo repository là mốc quan trọng, nhưng không luôn trùng startup

Với cách khởi tạo repository thông thường, Spring Data tạo implementation/proxy cho interface, xác định các phương thức cần được giải quyết như truy vấn và sử dụng cơ chế query lookup của module để tạo đối tượng truy vấn tương ứng.

Một derived query sai thuộc tính thường bị phát hiện trong quá trình này. Nếu repository là bean được khởi tạo sớm, lỗi thường khiến quá trình tạo application context thất bại dù ứng dụng chưa nhận request nào.

```text
Ứng dụng bắt đầu tạo context
             |
             v
Khám phá repository
             |
             v
Khởi tạo repository thực
             |
             v
Phân giải findByStatuz(...)
             |
             v
Không có thuộc tính statuz
             |
             v
Không tạo được repository / context thất bại
```

Nhưng nếu việc khởi tạo repository thực bị trì hoãn, cùng lỗi đó có thể xuất hiện khi một tác vụ đầu tiên cần sử dụng repository. Nguyên nhân vẫn là metadata truy vấn sai; chỉ có thời điểm kích hoạt việc kiểm tra đã thay đổi.

### 3.1. Được inject chưa chắc đã được kiểm tra đầy đủ

Một field repository không `null` có thể chỉ đang giữ một proxy trì hoãn khởi tạo. Vì vậy các nhận định sau không tương đương:

1. Spring đã đăng ký bean repository.
2. Spring đã inject một tham chiếu repository.
3. Repository đích đã được khởi tạo và các phương thức truy vấn đã được phân giải.
4. Một truy vấn cụ thể đã được thực thi thành công.
5. Kết quả truy vấn đã được đọc và xác nhận đúng nghiệp vụ.

Không nên dùng riêng kiểm tra “bean tồn tại” để kết luận phương thức truy vấn đã hợp lệ.

### 3.2. Không phải mọi phương thức đều đi qua suy diễn tên

Các phương thức đã có implementation từ repository cơ sở, chẳng hạn các thao tác CRUD được kế thừa, không phải những tên tùy ý để parser diễn giải lại. Repository fragment hoặc implementation tùy biến cũng có đường thực thi riêng.

Trước khi chẩn đoán “tên phương thức sai nhưng không thấy lỗi”, cần xác nhận framework có thực sự xem phương thức đó là một phương thức truy vấn cần phân giải hay không. Một implementation tùy biến có thể hoàn toàn không dùng cơ chế suy diễn tên.

## 4. Query lookup strategy quyết định thiếu truy vấn có phải lỗi hay không

Commons định nghĩa các khóa chiến lược trong `QueryLookupStrategy.Key`. Module lưu trữ triển khai chiến lược và quyết định khả năng hỗ trợ cụ thể.

| Chiến lược | Cách tìm truy vấn | Hệ quả khi không có khai báo |
| --- | --- | --- |
| `CREATE` | Tạo truy vấn từ tên phương thức | Không coi khai báo là nguồn cần tìm trước; tên phải suy diễn được |
| `USE_DECLARED_QUERY` | Chỉ tìm truy vấn đã khai báo theo cơ chế module hỗ trợ | Thiếu khai báo dẫn tới lỗi phân giải |
| `CREATE_IF_NOT_FOUND` | Tìm khai báo trước; nếu không có thì tạo từ tên | Thiếu khai báo có thể không gây lỗi nếu suy diễn thành công |

Trong Spring Data JPA, `CREATE_IF_NOT_FOUND` là lựa chọn mặc định khi không cấu hình khác. Không áp đặt mặc định hoặc mức hỗ trợ này cho mọi module Spring Data.

### 4.1. Cùng một phương thức, ba kết quả khác nhau

Xét phương thức không có implementation riêng:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);
```

Giả sử không có annotation truy vấn trực tiếp hoặc named query tương ứng:

- Với `CREATE`, module cố tạo truy vấn từ tên; nếu thuộc tính và toán tử được hỗ trợ, phương thức có thể hợp lệ.
- Với `USE_DECLARED_QUERY`, thiếu khai báo là lỗi, dù tên phương thức có thể suy diễn được.
- Với `CREATE_IF_NOT_FOUND`, module có thể chuyển sang suy diễn và tiếp tục hoạt động.

Do đó, “thiếu truy vấn khai báo” không đồng nghĩa “repository chắc chắn không khởi tạo được”. Cần đọc chiến lược đang có hiệu lực.

### 4.2. Tên nghiệp vụ tự do không phải một fallback hợp lệ

Xét ví dụ **Spring Data JPA** dự định dùng named query:

```java
List<PurchaseOrder> findForManualReview(OrderStatus status);
```

Theo quy ước tra cứu thông thường, Spring Data JPA tìm tên:

```text
PurchaseOrder.findForManualReview
```

Nếu khai báo đó không tồn tại hoặc không được nạp:

- `USE_DECLARED_QUERY` không có nguồn truy vấn để sử dụng.
- `CREATE_IF_NOT_FOUND` có thể chuyển sang suy diễn, nhưng tên `findForManualReview` không mô tả điều kiện hợp lệ trên domain đã cho.

Framework không suy ra được “manual review” phải tương ứng với trạng thái nào, khoảng thời gian nào hay điều kiện gì. Thiếu named query trong trường hợp này có thể dẫn tới lỗi phân tích tên ở bước fallback, khiến thông báo ngoài cùng trông giống một derived query sai thuộc tính.

Đây là lý do cần xem **toàn bộ đường phân giải truy vấn**, thay vì chỉ sửa tên thuộc tính theo gợi ý trong một thông báo lỗi rồi làm thay đổi ý định ban đầu.

### 4.3. Khai báo thiếu có thể tạo ra lỗi nghiệp vụ âm thầm

Giả sử named query dự định cho `findByStatus` còn chứa điều kiện loại trừ những đơn hàng không được phép hiển thị. Nếu khai báo bị thiếu nhưng tên phương thức suy diễn được, fallback có thể chỉ giữ điều kiện `status = ...`.

Ứng dụng lúc đó có thể:

1. Khởi tạo repository thành công.
2. Thực thi truy vấn thành công.
3. Trả kết quả sai yêu cầu vì thiếu một điều kiện bắt buộc.

Không có exception không đồng nghĩa truy vấn đúng. Nếu một nhóm repository bắt buộc có khai báo, có thể xem xét `USE_DECLARED_QUERY` cho phạm vi phù hợp. Đồng thời cần kiểm thử điều kiện nghiệp vụ, vì chiến lược tra cứu không xác nhận nội dung khai báo có đúng ý định hay không.

### 4.4. Không tìm thấy khác với tìm thấy nhưng sai

`CREATE_IF_NOT_FOUND` là fallback khi không tìm được một nguồn truy vấn khai báo phù hợp. Nó không phải cơ chế bỏ qua mọi khai báo lỗi.

Ví dụ, một truy vấn đã được chọn nhưng có JPQL sai không nên được kỳ vọng sẽ bị bỏ qua để chạy derived query thay thế. Nếu không phân biệt hai tình huống này, người bảo trì có thể sửa một lỗi binding hoặc cú pháp bằng cách thay chiến lược, trong khi nguyên nhân thật vẫn còn.

## 5. Truy vấn khai báo: điều gì có thể kiểm tra sớm?

Ví dụ phần này dùng **Spring Data JPA**. Domain có entity name `PurchaseOrder`, thuộc tính `status`, và bảng vật lý `purchase_orders`.

### 5.1. JPQL sai thuộc tính thường có thể bị phát hiện lúc tạo truy vấn

Ví dụ **cố ý sai**:

```java
import java.util.List;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.statuz = :status
        """)
    List<PurchaseOrder> loadByStatus(
            @Param("status") OrderStatus status);
}
```

Provider JPA có metadata entity nên có thể nhận ra `o.statuz` không tồn tại khi tạo hoặc kiểm tra đối tượng JPQL. Với quá trình khởi tạo repository sớm, lỗi loại này thường làm ứng dụng không khởi động được.

Tuy nhiên, không nâng nhận xét đó thành một cam kết rằng mọi phần ngữ nghĩa của mọi JPQL đều được xác minh xong trước khi gọi phương thức. Provider, hàm mở rộng, kiểu truy vấn và cách thực thi có thể ảnh hưởng thời điểm phát hiện.

### 5.2. Named query có thể được kiểm tra từ lúc khởi tạo hạ tầng JPA

Một named query khai báo trong entity hoặc mapping XML được nạp theo cơ chế của persistence unit. Provider có thể kiểm tra nó khi tạo `EntityManagerFactory`.

Điều này tạo ra hai nhóm lỗi khác nhau:

| Tình huống | Nơi cần xem xét |
| --- | --- |
| Khai báo named query có tồn tại nhưng JPQL sai | Lỗi có thể phát sinh khi provider nạp và kiểm tra metadata của persistence unit |
| Named query mà phương thức repository trông đợi không tồn tại | Lỗi hoặc fallback được quyết định trong cơ chế query lookup của repository |

Đổi bootstrap mode của repository không nhất thiết trì hoãn được một lỗi mà provider đã phát hiện khi tạo `EntityManagerFactory`. Cần xác định bean hoặc thành phần nào thực sự phát sinh nguyên nhân gốc.

Nếu có cả `@Query` trực tiếp lẫn named query tương ứng, trong Spring Data JPA chuỗi truy vấn trực tiếp trên phương thức được ưu tiên. Kiểm thử phương thức đó thành công chưa chắc đã chứng minh named query được dùng; ngoài ra provider vẫn có thể kiểm tra một khai báo named query khác trong lúc khởi tạo persistence unit.

### 5.3. Binding và kiểu kết quả có thể được kiểm tra ở nhiều mốc

Một số lỗi có thể nhận diện từ metadata:

- Placeholder có tên không khớp với tên tham số được khai báo.
- Số lượng tham số không phù hợp với toán tử suy diễn.
- Kiểu trả về hoặc loại tham số không được module hỗ trợ.
- Cấu trúc projection không phù hợp với cách dựng truy vấn.

Nhưng không phải mọi trường hợp đều được phát hiện sớm. Binding còn phụ thuộc giá trị thực tế, còn ánh xạ kết quả còn phụ thuộc dữ liệu thực tế hoặc metadata do kho dữ liệu trả về. Do đó cần phân biệt “có thể kiểm tra từ chữ ký” với “module/provider cụ thể đã kiểm tra ở mốc nào”.

Ví dụ một JPQL trả entity nhưng phương thức khai báo một kiểu kết quả không tương thích có thể thất bại khi tạo truy vấn có kiểu hoặc khi chuyển đổi kết quả. Không nên mặc định một thời điểm duy nhất cho mọi dạng mismatch.

## 6. Vì sao SQL native thường cần được chạy mới xác nhận được?

Ví dụ **Spring Data JPA**, câu SQL dưới đây cố ý dùng cột không tồn tại:

```java
@Query(
    value = """
        select o.*
        from purchase_orders o
        where o.statuz = :status
        """,
    nativeQuery = true
)
List<PurchaseOrder> loadUsingSql(@Param("status") String status);
```

Java compiler không hiểu chuỗi SQL. Metadata entity cũng không đủ để JPA kiểm tra toàn bộ cú pháp SQL, sự tồn tại của bảng/cột, quyền truy cập và các hàm đặc thù của mọi cơ sở dữ liệu.

Framework hoặc provider có thể thực hiện một phần phân tích trước khi chạy, nhưng điều đó không tương đương việc cơ sở dữ liệu đã chấp nhận câu lệnh. Cột `statuz` không tồn tại thường chỉ bị hệ quản trị từ chối khi câu lệnh được gửi để chuẩn bị hoặc thực thi.

Ngay cả khi thay thành cột đúng, truy vấn vẫn có thể lỗi do:

- Migration của môi trường chạy chưa tạo bảng hoặc cột cần thiết.
- Tài khoản kết nối thiếu quyền.
- Cú pháp hoặc hàm SQL không được hệ quản trị mục tiêu hỗ trợ.
- Kiểu dữ liệu của tham số không phù hợp với toán tử phía cơ sở dữ liệu.
- Cột, alias hoặc kiểu kết quả không phù hợp với entity/projection được yêu cầu.

Một repository khởi tạo thành công không chứng minh SQL native đã được kiểm tra trên schema thực tế.

### Liên hệ với phân trang

Truy vấn trả `Page<T>` có thể liên quan cả truy vấn lấy dữ liệu và truy vấn đếm. Một trang chạy được chưa chắc đã chứng minh mọi đường chạy của count query đều được thực hiện; framework có thể suy ra tổng trong một số trường hợp mà không cần gọi đếm.

Nếu count query bị sai, lỗi có thể chỉ xuất hiện khi gặp trường hợp cần thực thi nó. Kiểm tra phân trang phải bao gồm cả nội dung trang lẫn tổng số, với dữ liệu đủ để kích hoạt đường chạy cần kiểm tra. Đối với SQL native hoặc truy vấn phức tạp, càng không nên suy luận tính đúng của count query chỉ từ việc trang đầu có vài phần tử.

## 7. Bootstrap mode trong Spring Data JPA dịch chuyển mốc kiểm tra như thế nào?

Phần này là cơ chế riêng của **Spring Data JPA**, không phải một lựa chọn được cam kết cho mọi kho dữ liệu.

| Chế độ JPA | Ý nghĩa khái quát | Tác động thường thấy đối với lỗi truy vấn phát hiện khi khởi tạo repository |
| --- | --- | --- |
| `DEFAULT` | Repository thường được khởi tạo sớm, trừ khi có cấu hình trì hoãn thích hợp | Lỗi thường xuất hiện trong lúc tạo application context |
| `LAZY` | Sử dụng cơ chế trì hoãn, repository đích được khởi tạo khi có tương tác cần đến nó | Lỗi có thể chuyển tới lần tương tác đầu tiên, kể cả tương tác từ một bean lúc startup |
| `DEFERRED` | Trì hoãn trước, sau đó kích hoạt khởi tạo repository gắn với `ContextRefreshedEvent` | Hướng tới việc kiểm tra repository trong giai đoạn hoàn tất refresh context thay vì chờ một request đầu tiên |

Ví dụ cấu hình minh họa:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.config.BootstrapMode;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.orders.repository",
    bootstrapMode = BootstrapMode.DEFERRED
)
public class OrderRepositoryConfiguration {
}
```

Ứng dụng vẫn cần cấu hình hạ tầng JPA phù hợp. Ví dụ chỉ thể hiện lựa chọn bootstrap của repository trong package được quét; nó không định nghĩa chiến lược query lookup và không thực thi mọi truy vấn.

### 7.1. Lazy không có nghĩa chắc chắn lỗi ở request đầu tiên

Nếu một bean khởi động gọi repository, repository lazy có thể bị khởi tạo ngay trong startup. Nếu một tác vụ nền sử dụng trước request HTTP, lỗi có thể xuất hiện ở tác vụ nền. Nếu chưa có tương tác cần khởi tạo đích, lỗi có thể tiếp tục bị hoãn.

Vì thế, thay vì viết “LAZY làm lỗi xảy ra khi người dùng gọi API”, hãy mô tả chính xác hơn: **LAZY có thể dời lỗi khởi tạo đến lần tương tác kích hoạt repository thực**.

### 7.2. Deferred không chạy thử tất cả câu truy vấn

Khởi tạo deferred giúp đưa việc phân giải repository vào quá trình hoàn tất refresh context, nhưng không tự tạo dữ liệu, gửi mọi SQL native hay kiểm tra mọi tổ hợp tham số.

Nó cũng không thay thế tiêu chí readiness của một ứng dụng. Các kiểm tra khởi tạo repository, tình trạng kết nối và khả năng thực hiện tác vụ nghiệp vụ là những bằng chứng khác nhau, cần được thiết kế theo nhu cầu vận hành cụ thể.

### 7.3. Không áp dụng nhầm enum cho module khác

Sự tồn tại của `BootstrapMode` trong package Commons không chứng minh mọi annotation cấu hình repository đều có thuộc tính `bootstrapMode` với cùng hành vi. Khả năng sử dụng enum và thời điểm kiểm tra thực tế do module tích hợp quyết định.

## 8. Lỗi lúc gọi phương thức và lúc đọc kết quả

Một truy vấn có metadata hợp lệ vẫn có thể thất bại vì tình trạng kho dữ liệu hoặc giá trị cụ thể trong lần gọi.

### 8.1. Cardinality chỉ được xác nhận khi có kết quả thực tế

Ví dụ:

```java
Optional<PurchaseOrder> findByCustomerEmail(String email);
```

Giả sử chữ ký này được module hỗ trợ. Ý định là không có hoặc có một kết quả. Nếu cùng email có nhiều đơn hàng, truy vấn có thể thất bại vì số lượng kết quả vượt kỳ vọng.

Đây không phải lỗi tên phương thức hay thiếu truy vấn. Metadata có thể hoàn toàn hợp lệ; dữ liệu thực tế mới làm lộ ra việc hợp đồng cardinality không phù hợp với mô hình nghiệp vụ.

Nếu cần nhiều đơn hàng, nên chọn kiểu tập hợp. Nếu cần một đơn mới nhất, phải diễn đạt giới hạn và thứ tự theo cơ chế được module hỗ trợ. Nếu cần tính duy nhất thực sự, phải thiết kế ràng buộc dữ liệu thích hợp, không trông chờ `Optional` tự tạo ràng buộc.

### 8.2. Kiểu projection và dữ liệu có thể làm phát sinh lỗi muộn

Một truy vấn có thể được chấp nhận nhưng trả một giá trị không chuyển được sang kiểu projection dự kiến, thiếu alias cần thiết hoặc trả `null` vào vị trí không chấp nhận `null`. Thời điểm lỗi có thể là lúc materialize kết quả, lúc chuyển đổi, hoặc khi truy cập một thành phần của projection.

Auditing cũng không giải quyết vấn đề này: metadata thời điểm tạo/người tạo không tự làm truy vấn hợp lệ, không sửa kiểu kết quả và không bảo đảm một bộ lọc bắt buộc đã được áp dụng.

### 8.3. Stream không đồng nghĩa đã đọc hết dữ liệu

Một API trả `Stream<T>` có thể thực hiện một phần công việc khi gọi phương thức, còn việc đọc và chuyển đổi thêm dữ liệu diễn ra khi duyệt stream. Tùy module/provider, một lỗi có thể chỉ xuất hiện ở quá trình đó.

Khi kiểm thử, chỉ nhận được đối tượng stream chưa đủ; cần tiêu thụ phần kết quả liên quan và quản lý vòng đời tài nguyên theo yêu cầu của module. Điều này khác với việc yêu cầu mọi lỗi phải chờ đến lúc duyệt: một số lỗi vẫn có thể xảy ra ngay khi mở truy vấn.

## 9. Repository reactive: subscription là một mốc bổ sung

Với repository reactive, cần tách **phân giải phương thức truy vấn** khỏi **thực thi một publisher**.

```java
Flux<PurchaseOrder> orders = repository.findByStatus(OrderStatus.PAID);
```

Dòng này có thể trả một publisher mô tả công việc sẽ thực hiện. Với các thao tác có publisher dạng cold thường gặp, công việc truy cập dữ liệu diễn ra khi có subscription, rồi lỗi có thể được phát dưới dạng tín hiệu `onError`.

Tuy nhiên, không được kết luận rằng mọi lỗi đều chờ subscription:

- Lỗi tên phương thức có thể đã được phát hiện khi repository khởi tạo.
- Việc khởi tạo lazy hoặc kiểm tra đối số có thể ném lỗi trước khi trả publisher.
- Lỗi kết nối, thực thi và chuyển đổi dữ liệu có thể xuất hiện trong chuỗi reactive sau subscription.

```text
Khởi tạo repository
      |
      +--> Có thể lỗi metadata / phân giải truy vấn
      |
Gọi phương thức
      |
      +--> Có thể lỗi đồng bộ trước khi trả publisher
      |
Nhận publisher
      |
Đăng ký và tiêu thụ
      |
      +--> Có thể nhận onError từ thực thi / đọc dữ liệu
```

Một kiểm thử chỉ tạo publisher mà không subscribe không chứng minh truy vấn đã thực thi. Khi kiểm thử hành vi reactive, cần đăng ký, xác nhận phần tử hoặc tín hiệu hoàn tất/lỗi, và chờ kiểm chứng đó kết thúc bằng công cụ kiểm thử phù hợp với stack.

Không suy từ subscription của reactive repository sang hành vi JPA đồng bộ. Cũng không dùng `try/catch` quanh duy nhất dòng tạo publisher rồi kết luận đã bắt được toàn bộ lỗi có thể xuất hiện về sau trong pipeline.

## 10. Đọc exception theo nguyên nhân gốc và giai đoạn

Khi lỗi xảy ra lúc tạo repository, exception ngoài cùng thường phản ánh việc Spring không tạo được một bean hoặc không inject được dependency. Nó không nhất thiết là thông tin cụ thể nhất về truy vấn.

Cause chain minh họa, không phải định dạng cố định:

```text
Không tạo được service phụ thuộc repository
  -> Không tạo được bean repository
     -> Không tạo được truy vấn cho phương thức
        -> Không tìm thấy thuộc tính statuz trên PurchaseOrder
```

Các tên thường gặp như `BeanCreationException`, `QueryCreationException` hoặc `PropertyReferenceException` có thể giúp định hướng. Nhưng lớp wrapper, thứ tự bọc lỗi và thông điệp phụ thuộc module, provider, phiên bản và ngữ cảnh gọi. Không viết chẩn đoán chỉ dựa trên một chuỗi thông báo ngoài cùng.

### Quy trình chẩn đoán

1. **Xác định mốc phát sinh:** tạo context, tạo `EntityManagerFactory`, khởi tạo repository lazy, gọi phương thức hay tiêu thụ kết quả.
2. **Tìm phương thức và domain:** đọc tên phương thức, kiểu repository và kiểu domain trong cause chain.
3. **Xác định nguồn truy vấn thực sự:** suy diễn, annotation trực tiếp, named query hay implementation tùy biến.
4. **Đối chiếu query lookup strategy:** thiếu khai báo có làm fallback chạy hay không.
5. **Đối chiếu metadata đúng tầng:** thuộc tính Java cho derived query, entity cho JPQL, schema vật lý cho SQL.
6. **Xem nguyên nhân gốc:** lỗi thuộc tính, binding, provider, cơ sở dữ liệu, cardinality hay chuyển đổi kết quả.
7. **Xác nhận bằng kiểm tra nhỏ nhất có ý nghĩa:** khởi tạo repository cho lỗi metadata; thực thi trên kho dữ liệu phù hợp cho lỗi SQL/dữ liệu; tiêu thụ pipeline cho lỗi reactive.

Nếu lỗi chỉ xuất hiện ở một môi trường, cần so sánh cấu hình repository, nguồn named query được nạp, migration/schema và công nghệ lưu trữ thực tế. Không vội coi lazy initialization là nguyên nhân nghiệp vụ chỉ vì nó làm lỗi xuất hiện muộn hơn.

## 11. Thiết kế kiểm tra để phát hiện lỗi ở đúng tầng

### 11.1. Kiểm tra khởi tạo có mục tiêu gì?

Một kiểm tra tạo context có thể hữu ích để phát hiện:

- Derived query sai tên thuộc tính khi repository thật được khởi tạo.
- Thiếu khai báo với `USE_DECLARED_QUERY`.
- Một số lỗi JPQL hoặc metadata named query mà provider kiểm tra sớm.
- Cấu hình repository hoặc hạ tầng liên quan không hợp lệ.

Để kiểm tra có ý nghĩa, cần bảo đảm repository cần kiểm tra được quét và khởi tạo trong cấu hình thử nghiệm. Một context thành công vì package không được quét, bean bị mock hoặc chỉ tạo proxy lazy là một kết quả không đủ sức chứng minh truy vấn hợp lệ.

### 11.2. Kiểm tra thực thi cần xác nhận điều gì?

Với truy vấn được khai báo hoặc có logic nghiệp vụ quan trọng, kiểm tra tích hợp nên chuẩn bị dữ liệu phân biệt được các nhánh điều kiện rồi gọi phương thức thật.

Ví dụ yêu cầu là lọc trạng thái `PAID` từ một mốc thời gian:

| Dữ liệu thử | Kết quả mong đợi |
| --- | --- |
| `PAID`, thời điểm sau mốc | Được lấy |
| `PAID`, thời điểm đúng mốc với điều kiện `>=` | Được lấy |
| `PAID`, thời điểm trước mốc | Bị loại |
| `CANCELLED`, thời điểm sau mốc | Bị loại |
| Không có hàng phù hợp | Kết quả rỗng hợp lệ, không phải lỗi thiếu truy vấn |

Nếu named query có điều kiện bổ sung so với tên phương thức, dữ liệu thử phải có một hàng chỉ bị loại bởi điều kiện bổ sung đó. Nếu thiếu hàng này, kiểm thử có thể vẫn pass khi repository âm thầm dùng derived fallback.

### 11.3. SQL đặc thù cần môi trường kiểm tra phù hợp

Một cơ sở dữ liệu thay thế trong test có thể khác hệ quản trị mục tiêu về cú pháp, hàm, kiểu dữ liệu và collation. Vì vậy, test trên môi trường thay thế có giá trị trong phạm vi nó kiểm chứng, nhưng không chứng minh toàn bộ SQL native sẽ chạy đúng trên môi trường triển khai.

Ngược lại, một test schema trống chỉ tạo context cũng chưa xác nhận câu truy vấn đọc được bảng/cột thực tế. Chọn mức tích hợp dựa trên loại lỗi muốn phát hiện, thay vì chỉ tăng số lượng kiểm thử không chạm đến đường chạy liên quan.

### 11.4. Không kiểm tra lỗi dữ liệu bằng cách trông chờ startup thất bại

Các trường hợp như nhiều hàng cho kiểu trả về một kết quả, lỗi chuyển đổi một giá trị đặc biệt, mất kết nối giữa chừng hoặc count query chỉ chạy ở một nhánh phân trang cần được kích hoạt bằng dữ liệu và thao tác thích hợp.

Không thể chứng minh chúng không xảy ra chỉ bằng một lần ứng dụng khởi động thành công. Tương tự, publisher reactive cần được tiêu thụ, stream cần được duyệt và một đường phân trang cụ thể cần thật sự được đi qua.

## 12. Những ngộ nhận dễ gây sửa sai chỗ

| Nhận định | Cách hiểu chính xác hơn |
| --- | --- |
| “Java compile được thì tên truy vấn chắc đúng” | Compiler không phân tích ngữ nghĩa derived query hoặc chuỗi JPQL/SQL |
| “Không gọi phương thức thì nó không thể làm startup lỗi” | Repository khởi tạo sớm có thể phân giải các phương thức truy vấn trước lần gọi |
| “Đã inject repository nên tất cả truy vấn đã được kiểm tra” | Tham chiếu được inject có thể là proxy trì hoãn |
| “Thiếu named query luôn gây lỗi” | Fallback có thể suy diễn thành công tùy chiến lược |
| “`CREATE_IF_NOT_FOUND` chữa được mọi `@Query` lỗi” | Fallback do thiếu khai báo khác với bỏ qua một khai báo đã chọn nhưng sai |
| “Dùng lazy là đã sửa lỗi repository” | Lazy có thể chỉ dời thời điểm phát hiện |
| “Deferred chạy thử hết các câu truy vấn” | Khởi tạo và phân giải không đồng nghĩa thực thi mọi truy vấn với dữ liệu thật |
| “Context chạy được thì SQL native chắc đúng schema” | Nhiều kiểm tra SQL/schema chỉ xảy ra khi cơ sở dữ liệu xử lý câu lệnh |
| “Nhận được Flux nghĩa là truy vấn thành công” | Nhiều thao tác chỉ thực thi sau subscription và có thể phát `onError` |
| “Danh sách rỗng là thiếu truy vấn” | Truy vấn hợp lệ có thể không tìm thấy bản ghi; thiếu nguồn truy vấn là vấn đề khác |

## 13. Bài tập phân tích tình huống

### Tình huống 1: Đổi tên thuộc tính nhưng ứng dụng vẫn biên dịch

Domain đổi `createdAt` thành `submittedAt`, nhưng repository vẫn có `findByCreatedAtAfter(...)`. Ứng dụng JPA dùng repository khởi tạo sớm.

**Phân tích:** tên phương thức vẫn hợp lệ trong Java nên compile có thể thành công. Nếu không có nguồn khai báo khác được chọn và framework suy diễn từ tên, việc phân giải `createdAt` thường thất bại khi repository khởi tạo. Cần cập nhật phương thức và các caller theo ý nghĩa mới của thuộc tính.

Nếu đổi sang lazy, lỗi không tự biến mất; nó có thể chờ tới lần tương tác khởi tạo repository thực.

### Tình huống 2: Named query bị xóa nhưng test context vẫn xanh

Phương thức `findByStatus(...)` dự định dùng named query chứa thêm một điều kiện nghiệp vụ. Named query bị xóa, chiến lược là `CREATE_IF_NOT_FOUND`.

**Phân tích:** tên phương thức vẫn suy diễn được nên khởi tạo context có thể thành công. Cần kiểm tra nguồn truy vấn được chọn và thêm dữ liệu thử phân biệt điều kiện nghiệp vụ bổ sung. Có thể xem xét `USE_DECLARED_QUERY` nếu toàn bộ phạm vi repository cần bắt buộc dùng khai báo.

Không nên sửa test bằng cách chỉ yêu cầu bean repository khác `null`; điều đó không kiểm chứng được hành vi bị mất.

### Tình huống 3: Đã đổi sang deferred nhưng named query vẫn làm startup lỗi

Provider báo JPQL sai khi tạo `EntityManagerFactory`, dù repository JPA dùng `BootstrapMode.DEFERRED`.

**Phân tích:** lỗi phát sinh khi provider nạp metadata của persistence unit, không cần chờ repository phân giải phương thức. Deferred không cam kết dời mọi loại kiểm tra JPA. Cần sửa khai báo sai và xác nhận đúng nguyên nhân gốc, thay vì tiếp tục đổi bootstrap mode.

### Tình huống 4: SQL native chỉ lỗi ở lần gọi đầu

Context khởi tạo bình thường nhưng phương thức native query báo cột không tồn tại khi chạy.

**Phân tích:** truy vấn có thể chưa được hệ quản trị kiểm tra trên schema thật tại startup. Cần đối chiếu SQL với migration/schema và thực thi kiểm tra tích hợp phù hợp. Việc thêm một test chỉ tạo repository không thay thế được đường chạy SQL đang lỗi.

### Tình huống 5: Test reactive không nhận lỗi dù cơ sở dữ liệu không truy cập được

Test chỉ gọi phương thức để lấy `Flux`, rồi kết thúc mà không subscribe.

**Phân tích:** publisher có thể chưa thực hiện thao tác dữ liệu. Cần tiêu thụ publisher và xác nhận tín hiệu lỗi bằng công cụ kiểm thử reactive phù hợp. Đồng thời nhớ rằng lỗi metadata vẫn có thể xảy ra sớm ở giai đoạn khởi tạo repository, độc lập với subscription.

## 14. Các điểm cần nhớ

- Thời điểm phát hiện phụ thuộc nơi có đủ thông tin để kiểm tra: compiler, metadata repository, provider, kho dữ liệu hoặc bước tiêu thụ kết quả.
- Nhiều lỗi tên derived query và thiếu khai báo được phát hiện khi repository thực khởi tạo, nhưng khởi tạo repository không luôn trùng thời điểm ứng dụng bắt đầu chạy.
- Query lookup strategy quyết định việc thiếu khai báo gây lỗi hay dẫn tới suy diễn; fallback thành công vẫn có thể sai yêu cầu nghiệp vụ.
- JPQL, named query JPA, SQL native, bootstrap mode và reactive execution có các mốc kiểm tra khác nhau; không áp dụng một quy tắc chung cho mọi module.
- Kiểm tra khởi tạo, thực thi và hành vi bổ sung bằng chứng cho nhau. Mỗi kiểm tra cần thật sự đi qua giai đoạn mà loại lỗi cần phát hiện có thể xuất hiện.
