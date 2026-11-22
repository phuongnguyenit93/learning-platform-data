# Giao dịch giải quyết vấn đề cập nhật dữ liệu dở dang

## 1. Vấn đề: một nghiệp vụ có nhiều lần cập nhật

Giả sử hệ thống chuyển **200 đơn vị tiền** từ tài khoản A sang tài khoản B. Ban đầu A có 1.000, B có 500; tổng cộng 1.500. Một yêu cầu chuyển tiền gồm hai thay đổi dữ liệu **cùng thuộc một nghiệp vụ**:

1. Trừ 200 khỏi A: số dư A thành 800.
2. Cộng 200 vào B: số dư B thành 700.

Nếu ứng dụng hoặc cơ sở dữ liệu gặp lỗi **sau bước 1 nhưng trước khi hoàn tất bước 2**, mà mỗi câu lệnh SQL đã được ghi nhận riêng, trạng thái còn lại là A = 800 và B = 500. Tổng số dư chỉ còn 1.300; hệ thống đã ghi nhận **một nửa nghiệp vụ**. Ghi log báo lỗi hoặc cho người dùng bấm “thử lại” không tự động khôi phục số tiền thiếu.

| Tình huống | A | B | Tổng | Đánh giá |
| --- | ---: | ---: | ---: | --- |
| Trước chuyển | 1.000 | 500 | 1.500 | Hợp lệ |
| Sau khi chỉ trừ A | 800 | 500 | 1.300 | **Dở dang, sai quy tắc nghiệp vụ** |
| Sau khi cả hai bước thành công | 800 | 700 | 1.500 | Hợp lệ |
| Có lỗi và hoàn tác toàn bộ | 1.000 | 500 | 1.500 | Hợp lệ |

Đây là vấn đề **partial update**: các thao tác riêng lẻ có thể đúng về mặt SQL, nhưng trạng thái tổng thể sai vì chúng chưa được hoàn tất như một đơn vị.

## 2. Transaction giải quyết điều gì?

**Database transaction (giao dịch cơ sở dữ liệu)** gom những thay đổi liên quan thành một đơn vị thực thi có hai kết cục:

- **Commit:** toàn bộ thay đổi hợp lệ trong giao dịch được xác nhận.
- **Rollback:** các thay đổi chưa commit trong giao dịch bị hoàn tác về trạng thái trước giao dịch.

Với ví dụ chuyển tiền:

~~~text
Bắt đầu transaction
    |
    +-- UPDATE A: trừ 200
    |
    +-- UPDATE B: cộng 200
    |
    +-- Cả hai thành công? -- Có --> COMMIT --> A=800, B=700
                              |
                              Không / lỗi
                              |
                              v
                           ROLLBACK --> A=1000, B=500
~~~

Điểm trọng tâm là **Atomicity (tính nguyên tử)** trong ACID: trong phạm vi *cùng một giao dịch được cơ sở dữ liệu hỗ trợ*, hệ thống không xác nhận trạng thái “chỉ chạy xong một phần”. Transaction bảo vệ thay đổi giữa **bắt đầu** và **commit**; nó không có nghĩa mọi thao tác bên trong chắc chắn thành công, và cũng không tự sửa dữ liệu sai đã commit từ trước.

ACID đặt tính nguyên tử trong bức tranh rộng hơn:

| Thuộc tính | Ý nghĩa thực tế |
| --- | --- |
| **Atomicity** | Tất cả thay đổi trong một transaction cùng commit hoặc cùng rollback. Đây là giải pháp chính cho cập nhật dở dang. |
| **Consistency** | Giao dịch thành công phải duy trì các ràng buộc/bất biến đã được thiết kế (khóa chính, CHECK, quy tắc tổng tiền...). Transaction tự nó không phát minh ra quy tắc nghiệp vụ. |
| **Isolation** | Quy định các transaction đồng thời nhìn thấy và ảnh hưởng lẫn nhau ở mức nào; cần xét riêng hiện tượng đọc bẩn, cập nhật mất và các tranh chấp. |
| **Durability** | Sau khi commit thành công, cơ sở dữ liệu có trách nhiệm duy trì dữ liệu theo bảo đảm bền vững của hệ quản trị và cấu hình lưu trữ. |

**Phân biệt quan trọng:** rollback giải quyết lỗi *trước commit*. Nếu giao dịch đã commit mà ứng dụng mất kết nối trước khi nhận phản hồi, client có thể không biết kết quả. Gửi lại yêu cầu mù quáng có nguy cơ chuyển tiền hai lần; trường hợp này cần thêm **idempotency key** hoặc cơ chế nhận diện yêu cầu đã xử lý.

## 3. Vì sao hai lệnh UPDATE thông thường có thể gây lỗi dở dang?

Nhiều kết nối JDBC hoạt động ở chế độ `autoCommit = true`: một câu SQL thành công có thể được commit ngay khi kết thúc câu lệnh. Ví dụ tư duy sau đây *không phải một transaction bao trùm cả nghiệp vụ*:

~~~sql
UPDATE account SET balance = balance - 200 WHERE id = 1;
-- Nếu câu UPDATE trên đã commit và hệ thống lỗi tại đây...
UPDATE account SET balance = balance + 200 WHERE id = 2;
~~~

Câu SQL thứ hai thất bại không thể tự động “quay ngược” câu đầu đã commit. Trong JDBC thuần, người lập trình có thể tắt auto-commit, chủ động `commit()`/`rollback()` và khôi phục trạng thái kết nối đúng cách. Nhưng khi dùng Spring, ta thường giao trách nhiệm quản lý vòng đời transaction cho Spring để tránh lặp lại mã và bảo đảm một ranh giới nghiệp vụ rõ ràng.

## 4. Spring Framework quản lý transaction như thế nào?

Trong lập trình Spring theo mô hình imperative (Spring JDBC/JPA), cách phổ biến là đặt `@Transactional` trên **phương thức public của Spring service** đại diện cho một nghiệp vụ:

~~~java
@Service
public class TransferService {
    @Transactional
    public void transfer(/* nguồn, đích, số tiền */) {
        // 1. Trừ tiền nguồn
        // 2. Cộng tiền đích
        // Nếu có lỗi phù hợp quy tắc rollback, giao dịch được rollback.
    }
}
~~~

*Đoạn trên minh họa ranh giới nghiệp vụ, chưa phải chương trình Java độc lập.*

Theo cơ chế mặc định dựa trên **Spring AOP proxy**, khi một đối tượng khác gọi phương thức `transfer()` **thông qua Spring bean**:

1. Proxy đi qua transaction interceptor. `PlatformTransactionManager` thích hợp mở transaction mới hoặc tham gia transaction hiện hữu, tùy cấu hình.
2. Với JDBC, transaction manager quản lý connection và trạng thái transaction gắn với ngữ cảnh thực thi; `JdbcTemplate` sử dụng connection thuộc transaction đó khi cùng `DataSource`.
3. Phương thức nghiệp vụ thực hiện các câu lệnh SQL.
4. Khi phương thức kết thúc bình thường và transaction hiện hữu không bị đánh dấu rollback-only, Spring commit ở ranh giới mà nó quản lý. Nếu exception phù hợp quy tắc rollback thoát khỏi phương thức, Spring rollback (hoặc đánh dấu rollback-only nếu đang tham gia transaction của caller).

`@Transactional` không tự động tạo transaction ở mọi lời gọi Java: nếu tự `new TransferService(...)`, nếu gọi nội bộ bằng `this.someTransactionalMethod()` trong cùng bean, hoặc nếu cấu hình transaction manager/data source không đúng, có thể không đi qua proxy hoặc không bảo vệ các thao tác như mong đợi. Ranh giới service và kiểm thử rollback thực tế là điều cần thiết.

**Mặc định quan trọng:** Spring rollback đối với `RuntimeException` và `Error`; checked exception như `IOException` **không** mặc định yêu cầu rollback. Khi nghiệp vụ cần rollback với checked exception, cấu hình rõ `@Transactional(rollbackFor = IOException.class)` (và khai báo/điều khiển exception cho đúng Java). Việc bắt rồi nuốt exception bên trong transaction cũng có thể làm phương thức kết thúc bình thường, dẫn đến commit ngoài ý muốn.

## 5. Ví dụ thực hành: Spring Boot + JDBC + H2

Mục tiêu kiểm chứng trực tiếp hai trường hợp: **chuyển tiền thành công thì commit** và **đã trừ tiền nguồn nhưng tài khoản đích không tồn tại thì rollback**.

Tạo một dự án **Spring Boot, Java 17+ và Maven** bằng Spring Initializr, thêm các dependency **JDBC API / Spring JDBC**, **H2 Database** và **Spring Boot Starter Test**. Giữ cấu trúc package bên dưới; dự án có Maven Wrapper (`mvnw`, `mvnw.cmd`) do Initializr cung cấp. H2 ở đây là cơ sở dữ liệu **in-memory để học và chạy test**, không phải thiết kế lưu trữ cho hệ thống ngân hàng thực tế.

**Tệp 1 — `src/main/resources/schema.sql`**

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);
~~~

Cột `balance` dùng số nguyên (đơn vị tiền nhỏ nhất) để tránh sai số nhị phân của `double` khi tính tiền. `CHECK (balance >= 0)` là một lớp bảo vệ tại database. Với H2 embedded và cơ chế SQL initialization thông thường của Spring Boot, `schema.sql` được chạy khi khởi tạo database.

**Tệp 2 — `src/main/java/com/example/transactiondemo/TransactionDemoApplication.java`**

~~~java
package com.example.transactiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TransactionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransactionDemoApplication.class, args);
    }
}
~~~

**Tệp 3 — `src/main/java/com/example/transactiondemo/TransferService.java`**

~~~java
package com.example.transactiondemo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException(
                "Source account missing or insufficient balance"
            );
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalArgumentException("Target account missing");
        }
    }
}
~~~

Phân tích từng điểm then chốt:

- `@Transactional` bao quanh cả **hai** lần `jdbc.update`. Hai thao tác tham gia cùng database transaction do Spring quản lý.
- Câu trừ tiền có điều kiện `balance >= ?`, giúp từ chối trừ vượt số dư ngay ở database; điều kiện này cũng có ích khi nhiều yêu cầu cùng tác động đến một tài khoản.
- `JdbcTemplate.update(...)` trả về **số hàng bị ảnh hưởng**. Nếu tài khoản nguồn không hợp lệ/hết tiền hoặc tài khoản đích không tồn tại, service phát sinh unchecked exception để yêu cầu rollback.
- Ở lỗi tài khoản đích, lệnh trừ tiền nguồn **đã chạy** trước đó; chính rollback phải đưa số dư nguồn về như cũ. Vì vậy đây là phép thử thích hợp cho trường hợp cập nhật dở dang.
- Ví dụ giữ phạm vi **một database và một transaction manager**. Ứng dụng thật còn cần xác thực quyền chuyển tiền, chống chuyển trùng, audit, xử lý retry và quy tắc tiền tệ.

**Tệp 4 — `src/test/java/com/example/transactiondemo/TransferServiceTest.java`**

~~~java
package com.example.transactiondemo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransferServiceTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private TransferService service;

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM account");
        jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1L, 1000L);
        jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2L, 500L);
    }

    @Test
    void commitsWhenBothUpdatesSucceed() {
        service.transfer(1L, 2L, 200L);

        assertEquals(800L, balanceOf(1L));
        assertEquals(700L, balanceOf(2L));
    }

    @Test
    void rollsBackDebitWhenTargetIsMissing() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.transfer(1L, 99L, 200L)
        );

        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    private long balanceOf(long id) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            Long.class,
            id
        );
    }
}
~~~

Chạy tại thư mục gốc dự án:

~~~bash
# Linux/macOS
./mvnw test
~~~

~~~powershell
# Windows PowerShell
.\mvnw.cmd test
~~~

**Kết quả cần quan sát:** cả hai phương thức test đều pass. Kiểm thử thứ nhất xác nhận `(A, B) = (800, 700)` sau commit. Kiểm thử thứ hai gây lỗi *sau lệnh UPDATE đầu tiên*, rồi xác nhận `(A, B) = (1000, 500)`; điều đó chứng minh rollback được kích hoạt và không để lại bản cập nhật dở dang trong cơ sở dữ liệu. Không phụ thuộc vào một chuỗi stdout cố định vì log và thống kê build thay đổi theo phiên bản/công cụ.

Nếu bỏ `@Transactional` trong ví dụ này, hãy thử chạy lại test rollback trong môi trường H2 có auto-commit: lệnh cập nhật nguồn có thể đã commit trước khi lỗi đích xuất hiện, khiến phép kiểm tra `balanceOf(1L) == 1000` thất bại. Chỉ thay đổi annotation trong **môi trường học thử**, không dùng thao tác này trên dữ liệu thực.

## 6. Transaction boundary: đặt ở đâu để không bị “dở dang”?

Một transaction nên bao trùm **đủ các thao tác phải thành công cùng nhau**. Chẳng hạn:

- Tạo đơn hàng và trừ số lượng hàng trong **cùng database**: nếu không tạo được đơn, cần rollback phần trừ tồn kho.
- Ghi hóa đơn và chi tiết hóa đơn: nếu có dòng chi tiết không hợp lệ, không lưu “hóa đơn rỗng” ngoài ý muốn.
- Chuyển tiền giữa hai tài khoản cùng database: nếu không thể ghi có cho tài khoản đích, rollback phần ghi nợ.

Lớp **service** thường thể hiện trọn một use case, nên thuận lợi để đặt `@Transactional`. Không đặt annotation rời rạc chỉ trên từng repository update nếu mong muốn cả nghiệp vụ là một transaction: hai transaction nhỏ commit riêng vẫn có thể tạo ra trạng thái nửa chừng.

### Những điều dễ gây hiểu nhầm

| Tình huống | Hệ quả cần biết |
| --- | --- |
| Một phương thức gọi `this.otherMethod()` có `@Transactional` trong chính bean | Với proxy mặc định, lời gọi nội bộ không được interceptor chặn để mở transaction riêng. Gọi qua bean được Spring quản lý hoặc thiết kế lại ranh giới service. |
| Bắt và bỏ qua exception sau lần cập nhật đầu | Nếu phương thức kết thúc bình thường và chưa có đánh dấu rollback-only, transaction có thể commit phần thay đổi. Hãy phát sinh lại exception hoặc chủ động quyết định rollback. |
| Exception checked thoát ra | Mặc định không kích hoạt rollback chỉ vì là checked exception; dùng `rollbackFor` khi cần. |
| Gọi method `@Transactional` sau khi tự tạo đối tượng bằng `new` | Không có Spring AOP proxy quản lý lời gọi này. |
| Chỉ chú thích transaction trên thao tác thứ hai | Thao tác đầu đã commit riêng có thể không được hoàn tác khi thao tác hai lỗi. |
| Lời gọi HTTP, gửi email, ghi file hoặc gọi dịch vụ ngoài nằm trong method transaction | Rollback database **không** hoàn tác được các hiệu ứng bên ngoài đã xảy ra. Cần thiết kế phối hợp riêng (ví dụ transactional outbox, idempotency, saga khi phù hợp). |
| Method chạy lâu, chờ mạng hoặc giữ transaction qua luồng bất đồng bộ | Giữ khóa/kết nối lâu, tăng nguy cơ tranh chấp; transaction imperative theo thread không tự bao trùm công việc chạy ở thread khác. |

**Về propagation:** `@Transactional` mặc định dùng `REQUIRED`: nếu có transaction hiện hữu phù hợp, method tham gia transaction đó; nếu chưa có, Spring tạo mới. Vì thế “method chạy xong” **không nhất thiết** là thời điểm commit nếu nó đang tham gia transaction bên ngoài. `REQUIRES_NEW` có thể tạo transaction độc lập và commit riêng, nhưng dùng sai lại phá yêu cầu *cả nghiệp vụ cùng rollback*. Chỉ thay propagation khi đã xác định chính xác quy tắc commit/rollback cần có.

## 7. Giới hạn của transaction và thiết kế an toàn hơn

Transaction giải quyết **atomicity**, nhưng chưa đủ để xây hệ thống dữ liệu chính xác trong mọi điều kiện:

1. **Tranh chấp đồng thời:** hai yêu cầu cùng sửa một tài khoản còn cần SQL/locking/isolation phù hợp, thứ tự khóa nhất quán và xử lý deadlock/timeout. Lệnh `UPDATE ... WHERE balance >= ?` giúp chặn số dư âm trong ví dụ, nhưng không thay thế việc phân tích toàn bộ bất biến của hệ thống.
2. **Ràng buộc nghiệp vụ:** kiểm tra số hàng cập nhật, `CHECK`, khóa ngoại, unique constraint và kiểm tra dữ liệu đầu vào; transaction không tự phát hiện “chuyển sai người” nếu mọi lệnh SQL đều hợp lệ.
3. **Nhiều nguồn tài nguyên:** một local DB transaction không mặc nhiên bao trùm hai database độc lập, message broker hay HTTP API. Outbox/saga hoặc cơ chế phân tán thích hợp sẽ cần được cân nhắc.
4. **Lỗi sau commit và retry:** request ID/idempotency key và trạng thái xử lý giúp tránh thực thi lại cùng một lệnh nghiệp vụ sau khi client không nhận được phản hồi.
5. **Kiểm chứng thực tế:** luôn test ít nhất một lỗi *sau khi bước đầu đã ghi dữ liệu*, sau đó đọc lại database để kiểm tra không còn thay đổi dở dang.

## 8. Câu hỏi tự kiểm tra

1. Nếu đã trừ A thành công và câu lệnh cộng B thất bại, trạng thái nào là hợp lệ? **Đáp án:** rollback cả hai về A = 1.000, B = 500.
2. Vì sao hai câu SQL đều “thành công khi chạy riêng” vẫn chưa đủ? **Đáp án:** tính đúng đắn thuộc về **toàn bộ nghiệp vụ**, không thuộc từng câu lệnh riêng rẽ.
3. Khi đặt `@Transactional` trên hai method repository khác nhau mà không có transaction bao ngoài, có chắc nguyên tử không? **Không.** Mỗi method có thể commit độc lập.
4. Vì sao phải test exception tại bước thứ hai? **Vì** đó là lúc có một thay đổi trước đó cần được hoàn tác; test lỗi trước mọi UPDATE chưa chứng minh được rollback dữ liệu.
5. Transaction database có tự hủy email đã gửi không? **Không.** Email là hiệu ứng bên ngoài database transaction.

**Ghi nhớ:** xác định ranh giới nghiệp vụ trước, đặt một transaction bao quanh các thay đổi cần *cùng thành công hoặc cùng thất bại*, kiểm tra điều kiện và lỗi rõ ràng, rồi **chứng minh bằng test rollback**. Đây là cách Spring transaction ngăn việc lưu lại dữ liệu mới chỉ được cập nhật một phần.

### Tài liệu đối chiếu

- Spring Framework — [Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- Spring Framework — [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- Spring Boot — [SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)