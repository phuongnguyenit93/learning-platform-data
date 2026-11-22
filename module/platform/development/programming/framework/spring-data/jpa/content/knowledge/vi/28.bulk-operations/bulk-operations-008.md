# Cấu hình `batch_size`, `order_inserts` và `order_updates` trong Hibernate

Khi một nghiệp vụ cần lưu hoặc cập nhật nhiều entity, cách gọi repository trong vòng lặp có thể tạo ra rất nhiều lần gửi SQL tới cơ sở dữ liệu. Hibernate hỗ trợ **JDBC batching** để gom nhiều lần thực thi cùng dạng câu lệnh vào một batch JDBC. Ba cấu hình `hibernate.jdbc.batch_size`, `hibernate.order_inserts` và `hibernate.order_updates` giúp kiểm soát kích thước batch và sắp xếp các thao tác để tăng khả năng gom nhóm.

Các thiết lập này tác động đến cách Hibernate gửi câu lệnh SQL qua JDBC. Chúng không tự biến nhiều thao tác JPA thành một câu SQL bulk duy nhất, không thay thế transaction và cũng không bảo đảm hiệu năng tốt hơn trong mọi workload. Cần cấu hình, quan sát và đo lường trên đúng JDBC driver cùng hệ quản trị cơ sở dữ liệu của ứng dụng.

## 1. JDBC batching là gì?

Không bật batching, một vòng lặp lưu 100 entity có thể khiến Hibernate thực thi nhiều câu `INSERT` riêng biệt. Khi batching được bật, Hibernate có thể chuẩn bị các `PreparedStatement` cùng dạng, thêm các bộ tham số vào batch và gọi `executeBatch()` theo từng nhóm.

Ví dụ, với batch size là 50, Hibernate có thể gửi tối đa 50 lần thực thi của một dạng câu lệnh trong một batch JDBC. Nếu có 120 thao tác cùng dạng và tất cả đều đủ điều kiện gom nhóm, có thể hình thành các batch 50, 50 và 20. Đây là ví dụ minh họa; số batch thực tế phụ thuộc số lượng câu lệnh, kiểu SQL, thời điểm flush, chiến lược sinh ID, driver và provider.

JDBC batch thường vẫn là nhiều lần thực thi của cùng một prepared statement được gửi theo nhóm. Một số driver có thể viết lại batch thành dạng SQL tối ưu hơn, nhưng điều đó phụ thuộc driver và cấu hình riêng. Không nên mặc định rằng một batch luôn trở thành một câu `INSERT` nhiều dòng.

### Batching khác bulk operation như thế nào?

- **JDBC batching:** gom nhiều lần thực thi các câu lệnh có cùng cấu trúc SQL vào một batch. Hibernate vẫn quản lý từng entity và trạng thái persistence context.
- **JPQL bulk update/delete:** thực hiện một câu lệnh cập nhật hoặc xóa trực tiếp trên nhiều bản ghi. Cách này thường bỏ qua dirty checking của từng entity, lifecycle callback và có thể làm persistence context không còn đồng bộ với dữ liệu vừa cập nhật.
- **Batch xử lý theo lô ở tầng ứng dụng:** chia tập dữ liệu lớn thành nhiều phần để kiểm soát bộ nhớ và thời gian giao dịch. Cách này có thể kết hợp với JDBC batching.

Ba cách trên giải quyết các vấn đề khác nhau. Chủ đề của bài này tập trung vào JDBC batching của Hibernate.

## 2. Ba thuộc tính cấu hình chính

### 2.1. `hibernate.jdbc.batch_size`

Thuộc tính này đặt số lần thực thi JDBC tối đa mà Hibernate gom vào một batch. Giá trị `0` hoặc không cấu hình thường có nghĩa là JDBC batching bị tắt. Hãy đặt một số nguyên dương để bật batching.

Ví dụ:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
~~~

Với giá trị `50`, Hibernate có thể gom tối đa 50 thao tác cùng dạng SQL vào một batch. Giá trị này là giới hạn cho mỗi batch, không phải số lượng entity tối đa của một transaction. Một transaction có thể phát sinh nhiều batch.

Kích thước lớn hơn có thể giảm số lần trao đổi giữa ứng dụng và database, nhưng cũng có thể làm tăng bộ nhớ dùng cho batch, kích thước gói tin và thời gian thực thi mỗi đợt. Không có một giá trị tối ưu cho tất cả hệ thống. Có thể bắt đầu thử nghiệm ở khoảng 25 hoặc 50, sau đó đo với dữ liệu và driver thực tế.

### 2.2. `hibernate.order_inserts`

Khi một transaction lưu nhiều loại entity đan xen, thứ tự persist có thể tạo ra chuỗi SQL thay đổi liên tục giữa các bảng. Vì batch thường chỉ gom được các câu lệnh có cùng cấu trúc, việc xen kẽ này có thể làm các nhóm batch nhỏ hơn.

Bật `hibernate.order_inserts` để Hibernate sắp xếp các thao tác insert theo cách giúp các insert cùng loại entity được thực thi gần nhau hơn. Nhờ đó, Hibernate có thêm cơ hội gom chúng vào cùng batch.

~~~properties
spring.jpa.properties.hibernate.order_inserts=true
~~~

Ví dụ ứng dụng persist lần lượt `Book`, `Author`, `Book`, `Author`. Khi bật sắp xếp insert, Hibernate có thể nhóm các insert cho cùng loại entity thay vì giữ nguyên thứ tự gọi persist. Thứ tự SQL thực tế do Hibernate quản lý và có thể khác thứ tự thao tác trong mã Java.

### 2.3. `hibernate.order_updates`

Bật `hibernate.order_updates` để Hibernate sắp xếp các thao tác update, thường theo loại entity và khóa chính, nhằm tăng khả năng gom các câu update cùng dạng vào batch. Việc sắp xếp theo thứ tự ổn định cũng có thể giảm khả năng deadlock trong một số tình huống nhiều transaction cùng cập nhật các bản ghi.

~~~properties
spring.jpa.properties.hibernate.order_updates=true
~~~

Thiết lập này không loại bỏ hoàn toàn deadlock và không thay thế việc thiết kế thứ tự khóa, transaction ngắn hoặc chiến lược retry. Nó cũng có chi phí sắp xếp; hãy đo hiệu quả trên workload thật.

## 3. Cấu hình trong Spring Boot

Với ứng dụng Spring Boot sử dụng Hibernate làm JPA provider, có thể khai báo các thuộc tính trong `application.properties`:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Hoặc dùng `application.yml`:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
~~~

Spring Boot chuyển các thuộc tính dưới `spring.jpa.properties` xuống Hibernate. Nếu cấu hình trực tiếp Hibernate mà không dùng Spring Boot, tên thuộc tính tương ứng là `hibernate.jdbc.batch_size`, `hibernate.order_inserts` và `hibernate.order_updates`.

Các thuộc tính trên là cấu hình riêng của Hibernate. Nếu ứng dụng dùng JPA provider khác, không được giả định rằng provider đó hiểu hoặc áp dụng chúng.

## 4. Ví dụ lưu nhiều entity trong một transaction

Giả sử dự án có entity `Book` và repository Spring Data JPA. Có thể dùng `EntityManager` để lưu theo lô và giải phóng persistence context định kỳ:

~~~java
import java.util.List;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookImportService {
    private final EntityManager entityManager;

    public BookImportService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void importBooks(List<Book> books) {
        int flushInterval = 50;

        for (int i = 0; i < books.size(); i++) {
            entityManager.persist(books.get(i));

            if ((i + 1) % flushInterval == 0 || i + 1 == books.size()) {
                entityManager.flush();
                entityManager.clear();
            }
        }
    }
}
~~~

Ví dụ này là đoạn mã service cần đặt trong dự án Spring Boot có entity `Book`, Jakarta Persistence và cấu hình Hibernate ở phần trước; nó không phải chương trình Java độc lập để chạy bằng `javac` đơn lẻ.

Quá trình hoạt động:

1. `persist()` đưa entity mới vào persistence context. Hibernate theo dõi các entity này và chuẩn bị thao tác insert.
2. Khi đủ 50 entity, `flush()` đồng bộ các thay đổi đang chờ xuống database. Với cấu hình batching, Hibernate có thể gửi các insert đủ điều kiện thành batch.
3. `clear()` xóa toàn bộ entity đang được quản lý khỏi persistence context, giúp hạn chế bộ nhớ tăng liên tục trong một lần import lớn.
4. Điều kiện cuối vòng lặp xử lý cả phần còn dư nếu số lượng entity không chia hết cho 50.

`flush()` không đồng nghĩa với `commit()`. Nó gửi các thay đổi đang chờ xuống database trong transaction hiện tại; transaction vẫn có thể rollback sau đó. `clear()` làm tất cả entity đang managed trong persistence context trở thành detached. Vì vậy, chỉ nên dùng cách này khi có thể tách riêng công việc import và không cần tiếp tục thao tác với các entity đã bị detach.

Giá trị `flushInterval` trong ví dụ được đặt bằng `batch_size` để dễ theo dõi. Hai giá trị này có mục đích khác nhau: `hibernate.jdbc.batch_size` giới hạn số thao tác trong một batch JDBC, còn `flushInterval` quyết định khi nào ứng dụng yêu cầu Hibernate flush và clear persistence context. Có thể chọn khoảng flush khác sau khi đo lường.

## 5. Lưu ý quan trọng về chiến lược sinh ID

Một nguyên nhân phổ biến khiến insert batching không hoạt động như mong đợi là chiến lược sinh khóa chính `IDENTITY`.

Với `GenerationType.IDENTITY`, Hibernate cần thực hiện insert để database tạo ID tự tăng và trả ID về. Vì cần ID ngay sau insert, Hibernate thường không thể trì hoãn và gom các insert theo cách JDBC batching thông thường. Do đó, insert batching bị vô hiệu hóa đối với entity dùng IDENTITY trong Hibernate.

Trên database hỗ trợ sequence, `GenerationType.SEQUENCE` thường phù hợp hơn cho insert batching vì Hibernate có thể lấy ID trước khi gửi insert. Ví dụ khai báo:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;

@Entity
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "book_seq")
    @SequenceGenerator(
        name = "book_seq",
        sequenceName = "book_seq",
        allocationSize = 50
    )
    private Long id;

    // Các thuộc tính và phương thức của entity
}
~~~

Đây là ví dụ cấu hình entity, cần điều chỉnh tên sequence và chiến lược ID theo database đang sử dụng. `allocationSize` liên quan đến cách provider cấp phát ID từ sequence; hãy bảo đảm cấu hình sequence ở database tương thích với Hibernate. Không nên đổi IDENTITY sang SEQUENCE nếu database hoặc kiến trúc hiện tại không hỗ trợ.

## 6. Batch các thao tác update

Batch update có thể hoạt động khi Hibernate phát hiện thay đổi trên các entity đang được quản lý và flush chúng xuống database. Ví dụ:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookPriceService {
    private final BookRepository bookRepository;

    public BookPriceService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public void increasePrices(BigDecimal rate) {
        List<Book> books = bookRepository.findAll();

        for (Book book : books) {
            book.setPrice(book.getPrice().multiply(rate));
        }
    }
}
~~~

Đoạn mã giả định `Book` có `getPrice()` và `setPrice(...)`. Các entity được tải trong transaction đang managed; khi flush hoặc commit, Hibernate dùng dirty checking để xác định entity cần update. Với `hibernate.jdbc.batch_size` và `hibernate.order_updates` phù hợp, các update có cùng cấu trúc SQL có thể được gom batch.

Ví dụ `findAll()` chỉ phù hợp với tập dữ liệu nhỏ. Nếu số lượng bản ghi lớn, không nên tải tất cả entity vào bộ nhớ cùng lúc. Hãy dùng phân trang hoặc truy vấn theo từng khoảng khóa, xử lý theo chunk, và kiểm soát persistence context bằng flush/clear.

`hibernate.order_updates=true` sắp xếp các update do Hibernate quản lý; nó không làm cho một câu JPQL bulk update trở thành batch update. Nếu dùng `@Modifying` với JPQL `UPDATE`, database thực hiện một câu lệnh bulk riêng. Sau bulk update, cần chú ý persistence context có thể còn giữ trạng thái cũ; cân nhắc clear hoặc refresh phù hợp.

## 7. Khi nào batching không đạt hiệu quả?

- **Dùng IDENTITY cho ID của entity insert.** Hibernate thường phải insert ngay để lấy khóa chính nên không thể JDBC batch các insert đó.
- **SQL không cùng cấu trúc.** Những câu lệnh cập nhật các cột khác nhau hoặc thuộc bảng khác nhau không thể luôn gom vào cùng một batch. `order_inserts` và `order_updates` giúp gom nhóm nhưng không làm các câu SQL khác nhau trở thành giống nhau.
- **Không có transaction phù hợp.** Batch cần được thực thi trong ngữ cảnh giao dịch và flush phù hợp. Gọi từng thao tác trong các transaction quá ngắn có thể làm mất cơ hội gom nhóm.
- **Batch size không phù hợp.** Batch quá nhỏ có thể không giảm đủ số lần trao đổi; batch quá lớn có thể tăng bộ nhớ và thời gian xử lý. Hãy benchmark.
- **Driver hoặc database có giới hạn riêng.** Cần kiểm tra khả năng hỗ trợ batching, giới hạn tham số, kích thước gói tin và tùy chọn viết lại batch của driver.
- **Persistence context tăng quá lớn.** Lưu hàng trăm nghìn entity mà không flush/clear theo chunk có thể gây áp lực bộ nhớ, dù JDBC batching đã bật.
- **Dùng provider không phải Hibernate.** Các thuộc tính bắt đầu bằng `hibernate.` không phải tùy chọn JPA chuẩn.

Ngoài ra, việc sắp xếp câu lệnh có thể làm thay đổi thứ tự SQL so với thứ tự gọi `persist()` hoặc thay đổi entity trong Java. Nếu hệ thống có trigger hoặc logic phụ thuộc vào thứ tự câu lệnh, hãy kiểm tra tác động trước khi bật ordering.

## 8. Cách kiểm tra batching thực sự hoạt động

Không nên kết luận batching hoạt động chỉ vì đã thêm ba thuộc tính vào file cấu hình. Hãy kiểm tra bằng môi trường có Hibernate, JDBC driver và database tương ứng với production:

1. Xác nhận ứng dụng thực sự dùng Hibernate và các thuộc tính được nạp từ đúng profile cấu hình.
2. Tạo một transaction lưu số lượng entity lớn hơn batch size, ví dụ 120 entity với batch size 50.
3. Bật log SQL hoặc dùng công cụ quan sát JDBC để xem các prepared statement và lời gọi batch. Chỉ nhìn số dòng SQL log chưa chắc xác định được số lần `executeBatch()`.
4. Dùng Hibernate statistics hoặc công cụ giám sát JDBC/database để quan sát số prepared statement, batch execution, thời gian và số lần round trip nếu công cụ cung cấp.
5. So sánh thời gian, throughput và mức sử dụng bộ nhớ khi tắt/bật batching trên cùng dữ liệu, cùng database và điều kiện tải tương đương.
6. Kiểm tra riêng insert và update; nếu insert không batch, xác minh trước tiên chiến lược sinh ID.

Trong Spring Boot có thể bật thống kê Hibernate trong môi trường kiểm thử bằng:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Không nên bật log quá chi tiết hoặc thống kê tốn tài nguyên một cách mặc định trên production nếu chưa đánh giá tác động. Các con số trong môi trường H2 hoặc database giả lập cũng không thay thế phép đo trên hệ quản trị và driver thực tế.

## 9. Quy trình cấu hình thực tế

1. Xác định workload có nhiều insert, update hay cả hai; xác định entity và bảng thường được ghi.
2. Bật `hibernate.jdbc.batch_size` với một giá trị khởi đầu vừa phải, chẳng hạn 25 hoặc 50.
3. Bật `hibernate.order_inserts=true` nếu workload có nhiều insert thuộc nhiều entity type hoặc insert đan xen.
4. Bật `hibernate.order_updates=true` nếu workload có nhiều update và muốn tăng khả năng gom batch; kiểm tra thêm tác động đến deadlock và thứ tự câu lệnh.
5. Kiểm tra ID generator, đặc biệt tránh kỳ vọng insert batching với `IDENTITY`.
6. Với import lớn, đặt transaction hợp lý và chia chunk để flush/clear persistence context có kiểm soát.
7. Đo lại bằng JDBC driver và database mục tiêu; điều chỉnh batch size dựa trên throughput, latency, bộ nhớ và giới hạn của database.

| Thuộc tính | Vai trò | Điều cần kiểm tra |
|---|---|---|
| `hibernate.jdbc.batch_size` | Số lần thực thi JDBC tối đa trong một batch | Driver hỗ trợ, kích thước batch, số round trip |
| `hibernate.order_inserts` | Sắp xếp insert để gom các thao tác cùng loại | Insert có cùng cấu trúc SQL, ID generator |
| `hibernate.order_updates` | Sắp xếp update để tăng khả năng batching | Số update, thứ tự khóa, deadlock và chi phí sắp xếp |

Khi được cấu hình đúng, JDBC batching giúp Hibernate giảm chi phí gửi nhiều câu SQL riêng lẻ. Hiệu quả phụ thuộc khả năng gom các câu lệnh cùng dạng, chiến lược sinh ID, transaction, persistence context, driver và database. Hãy coi ba thuộc tính này là công cụ tối ưu cần đo lường, không phải công tắc tự động bảo đảm mọi thao tác hàng loạt đều nhanh hơn.