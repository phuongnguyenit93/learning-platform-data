# Ranh giới giao dịch và một đơn vị công việc nghiệp vụ

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định một **đơn vị công việc nghiệp vụ** (business unit of work): tập thay đổi phải cùng thành công hoặc cùng thất bại để giữ đúng quy tắc nghiệp vụ.
- Chọn **ranh giới giao dịch** (transaction boundary): đoạn xử lý nào bắt đầu, tham gia và kết thúc một giao dịch dữ liệu.
- Đặt `@Transactional` vào đúng tầng trong Spring Framework, giải thích lúc nào commit/rollback thực sự xảy ra.
- Phân biệt tính nguyên tử của một giao dịch CSDL với quy trình trải qua nhiều hệ thống; nhận diện các lỗi do chia giao dịch quá nhỏ hoặc giữ giao dịch quá lâu.
- Kiểm chứng ranh giới bằng một tình huống thành công và một tình huống lỗi có rollback.

Bài tập trung vào thiết kế ranh giới, không nhằm đi sâu vào toàn bộ API isolation, transaction propagation hay mô hình giao dịch phân tán.

## 2. Đơn vị công việc nghiệp vụ là gì?

Một yêu cầu từ người dùng thường chứa nhiều thao tác kỹ thuật nhưng chỉ biểu thị **một ý định nghiệp vụ**. Ví dụ, chuyển 100 đơn vị tiền từ tài khoản A sang B có thể đòi hỏi:

1. Kiểm tra số tiền và tài khoản hợp lệ.
2. Trừ 100 khỏi A, bảo đảm A không âm.
3. Cộng 100 vào B.
4. Ghi một bản ghi lịch sử chuyển tiền.

Nếu bước 2 thành công mà bước 3 hoặc 4 thất bại, hệ thống không được để tiền “biến mất” hoặc để lại một lần chuyển chưa hoàn chỉnh. Vì vậy, nếu cả bốn thay đổi nằm trong **cùng một CSDL hỗ trợ giao dịch**, chúng thường là một đơn vị công việc cần atomic commit.

**Business unit of work** là cách ta nhóm những thay đổi theo một kết quả nghiệp vụ có ý nghĩa. **Database transaction** là cơ chế kỹ thuật có thể thực thi sự nguyên tử của nhóm thay đổi trong một phạm vi tài nguyên giao dịch nhất định.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ chuyển tiền |
| --- | --- | --- |
| Business operation / use case | Người dùng muốn đạt kết quả gì? | Chuyển tiền A → B |
| Business invariant | Điều kiện nào phải luôn đúng ở trạng thái được commit? | Số dư không âm; tổng tiền được bảo toàn nếu không có phí |
| Unit of work | Những thay đổi nào phải cùng thành công? | Ghi nợ, ghi có, lịch sử |
| Transaction boundary | Cơ chế DB bao bọc các thay đổi từ đâu đến đâu? | Từ lúc service bắt đầu giao dịch đến khi hoàn tất các thao tác DB |
| Commit / rollback | Kết quả kỹ thuật của giao dịch là gì? | Ghi bền toàn bộ thay đổi hoặc hủy toàn bộ thay đổi trong phạm vi giao dịch |

Không mặc định rằng một HTTP request bằng một transaction: một request có thể chỉ đọc, có thể chứa nhiều bước độc lập, hoặc có thể điều phối một quy trình kéo dài nhiều phút. Ngược lại, một thao tác nghiệp vụ có thể được kích hoạt từ HTTP, job, message consumer hoặc CLI nhưng cùng chia sẻ một phương thức application service mang ý nghĩa nghiệp vụ.

### Tính nguyên tử và tính nhất quán

Trong ACID, **Atomicity** nói rằng các thay đổi thuộc một giao dịch được commit cùng nhau hoặc rollback cùng nhau. **Consistency** yêu cầu trạng thái sau commit thỏa các ràng buộc đã được thiết kế, chẳng hạn khóa chính, khóa ngoại, `CHECK`, điều kiện số dư và quy tắc nghiệp vụ. Một transaction không tự phát minh ra quy tắc đúng: lập trình viên vẫn phải kiểm tra nghiệp vụ và dùng constraint phù hợp.

**Isolation** là một vấn đề khác: hai giao dịch đồng thời có thể ảnh hưởng đến nhau. Có transaction bao quanh không đồng nghĩa mọi race condition tự biến mất. **Durability** do CSDL đảm bảo theo cấu hình và cam kết lưu trữ của nó. Ranh giới hợp lý giúp đạt atomicity; để đúng trong cạnh tranh đồng thời còn cần khóa, câu lệnh cập nhật có điều kiện, version, isolation phù hợp và đôi khi retry.

## 3. Đặt ranh giới ở đâu trong ứng dụng Spring?

Thiết kế thường dùng cho ứng dụng imperative với JDBC/JPA:

```text
HTTP / Message / Job
       |
       v
Controller / Adapter  -- ánh xạ request, xác thực, trả response
       |
       v
Application Service  -- điều phối một use case; @Transactional
       |
       +--> Repository A  -- đọc/ghi dữ liệu
       +--> Repository B  -- đọc/ghi dữ liệu
       +--> Repository C  -- đọc/ghi dữ liệu
       |
       v
Commit nếu hoàn tất; rollback nếu có lỗi theo quy tắc transaction
```

Ranh giới là **quyết định nghiệp vụ tại tầng service**, không đơn giản là đánh dấu tất cả repository bằng `@Transactional`. Một phương thức service như `transferMoney`, `placeOrder` hay `confirmReservation` đủ rõ để thể hiện “điểm bắt đầu/điểm kết thúc” của lần thay đổi nhất quán.

- **Quá hẹp:** mỗi repository tự commit trước khi service hoàn tất; thao tác thứ hai lỗi nhưng thao tác đầu đã bền vững.
- **Quá rộng:** bao quanh việc gọi HTTP, gửi email, chờ người dùng hoặc tính toán lâu; connection và lock bị giữ lâu, tăng contention/timeout và rủi ro deadlock.
- **Hợp lý:** kiểm tra đầu vào rẻ có thể làm trước; các bước đọc/ghi cần nhất quán nằm trong giao dịch; kết quả hoặc sự kiện ra hệ thống ngoài được xử lý theo cơ chế phù hợp sau commit.

Ví dụ, một thao tác đặt hàng trong **một DB** có thể cần lưu đơn hàng, dòng hàng, trừ tồn kho và bản ghi outbox trong cùng transaction. Nhưng gửi email hoặc gọi cổng thanh toán không tự động được rollback theo transaction đó.

### “Một use case = một transaction” chỉ là điểm xuất phát

Đó là heuristic hữu ích cho thao tác ngắn, dùng một CSDL. Không ép một workflow gồm nhiều dịch vụ, nhiều CSDL độc lập, nhiều lượt tương tác hoặc chạy hàng giờ vào một transaction duy nhất. Những workflow đó cần chia thành các bước bền vững, có trạng thái, khả năng khôi phục, idempotency và cơ chế bù trừ khi phù hợp.

## 4. Spring triển khai ranh giới này như thế nào?

Với **giao dịch imperative** và cấu hình mặc định dùng proxy, Spring chặn lời gọi từ bean bên ngoài vào phương thức `@Transactional`. `TransactionInterceptor` phối hợp với `PlatformTransactionManager`:

1. Xác định có giao dịch đang tồn tại và quy tắc propagation.
2. Nếu cần, mở giao dịch vật lý trên tài nguyên dữ liệu, hoặc tham gia giao dịch hiện có.
3. Gọi phần thân phương thức.
4. Khi phương thức kết thúc, commit hoặc rollback theo trạng thái giao dịch và quy tắc exception.
5. Dọn tài nguyên/synchronization gắn với luồng.

Với JDBC và một `DataSource`, `JdbcTemplate` dùng kết nối được Spring quản lý, nên nhiều câu SQL trong cùng giao dịch tham gia cùng transaction. Với JPA, Spring có thể quản lý `EntityManager` và đồng bộ các thay đổi vào transaction qua flush/commit. Điểm quan trọng là **đọc/ghi phải thực sự tham gia cùng tài nguyên và transaction manager**; hai kết nối hoặc hai transaction manager độc lập không trở thành một atomic transaction chỉ vì chung một tên phương thức.

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders, InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder(OrderRequest request) {
        inventory.reserve(request.items());
        orders.save(request);
    }
}
```

Đoạn trên là **minh họa kiến trúc**, không phải chương trình độc lập: các kiểu `OrderRepository`, `InventoryRepository` và `OrderRequest` do ứng dụng định nghĩa. Nếu hai repository dùng cùng transaction manager phù hợp, lỗi runtime trong `orders.save` khiến các thay đổi DB của `inventory.reserve` cùng bị rollback. Nếu `inventory.reserve` thực chất gọi HTTP sang hệ thống khác, kết luận đó không còn đúng.

**Mặc định quan trọng của `@Transactional` trong Spring Framework 6.x**:

- `propagation = REQUIRED`: tham gia giao dịch có sẵn; nếu chưa có thì tạo giao dịch mới.
- `isolation = DEFAULT`: tuân theo isolation mặc định của tài nguyên.
- `readOnly = false`; `timeout` theo cấu hình transaction system (hoặc không có nếu không hỗ trợ).
- `RuntimeException` và `Error` được rollback mặc định; một **checked exception** thường không kích hoạt rollback trừ khi cấu hình, chẳng hạn `@Transactional(rollbackFor = IOException.class)`.
- Với proxy mode, lời gọi **từ bean khác đi qua proxy** mới kích hoạt advice. `this.otherTransactionalMethod()` trong cùng đối tượng không tự tạo một ranh giới giao dịch mới.

Bối cảnh ảnh hưởng đến quyết định: `REQUIRES_NEW` tạo giao dịch vật lý độc lập và có thể commit dù giao dịch ngoài rollback; `NESTED` dùng savepoint khi transaction manager và tài nguyên hỗ trợ. Không dùng hai chế độ đó như cách vá một service có ranh giới sai. `readOnly = true` là tín hiệu tối ưu/hint đối với công cụ và driver tương ứng, **không** phải cơ chế bảo vệ dữ liệu tuyệt đối. Transaction imperative gắn với luồng thực thi, không tự truyền sang `@Async` hoặc thread mới. Ứng dụng reactive dùng cơ chế context khác.

## 5. Ví dụ chạy được: chuyển tiền bằng Spring Boot, JDBC và H2

Ví dụ nhỏ này chỉ dùng **một CSDL H2** và số dư nguyên để dễ kiểm tra; trong hệ thống tiền tệ thật cần biểu diễn bằng đơn vị nhỏ nhất hoặc kiểu thập phân thích hợp, validation, quy tắc đồng thời và audit đầy đủ. Mục tiêu là chứng minh ranh giới transaction.

Cấu trúc dự án:

```text
transaction-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/transactions/
    │   ├── TransferApplication.java
    │   └── TransferService.java
    └── resources/
        ├── schema.sql
        └── data.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'transaction-boundary-demo'
```

**`build.gradle`** — dùng Java 17 và Spring Boot 3.3.13 để tái hiện ví dụ; Gradle 8.x, JDK 17+.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance INT NOT NULL CHECK (balance >= 0)
);
```

**`src/main/resources/data.sql`**

```sql
INSERT INTO account (id, balance) VALUES (1, 500), (2, 100);
```

Spring Boot khởi tạo `schema.sql` và `data.sql` mặc định với H2 in-memory. Không cần web server hay controller cho bài thử này.

**`src/main/java/demo/transactions/TransferService.java`**

```java
package demo.transactions;

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
    public void transfer(long fromId, long toId, int amount, boolean failForDemo) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Yêu cầu chuyển tiền không hợp lệ");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Nguồn không tồn tại hoặc không đủ tiền");
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Đích không tồn tại");
        }

        // Lỗi xảy ra sau CẢ HAI câu lệnh UPDATE, trước lúc commit.
        if (failForDemo) {
            throw new IllegalStateException("Mô phỏng lỗi sau khi cập nhật");
        }
    }
}
```

Hai lệnh `jdbc.update` trên cùng tham gia transaction do proxy tạo khi bean khác gọi `transfer`. Điều kiện `balance >= ?` trong câu `UPDATE` là một hàng rào quan trọng chống ghi nợ vượt số dư trong tình huống cạnh tranh đồng thời; vẫn cần thiết kế thứ tự cập nhật/khóa và retry phù hợp cho tải thực tế. Không dùng tham số `failForDemo` trong API nghiệp vụ thật: nó chỉ minh họa rollback.

**`src/main/java/demo/transactions/TransferApplication.java`**

```java
package demo.transactions;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TransferApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransferApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService service, JdbcTemplate jdbc) {
        return args -> {
            service.transfer(1L, 2L, 100, false);
            show("Sau chuyển thành công", jdbc);

            try {
                service.transfer(1L, 2L, 50, true);
            } catch (IllegalStateException ex) {
                System.out.println("Lỗi giả lập: " + ex.getMessage());
            }

            show("Sau lần bị rollback", jdbc);
        };
    }

    private static void show(String label, JdbcTemplate jdbc) {
        Integer balanceA = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = 1", Integer.class
        );
        Integer balanceB = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = 2", Integer.class
        );
        System.out.printf("%s: A=%d, B=%d%n", label, balanceA, balanceB);
    }
}
```

Chạy tại thư mục dự án bằng Gradle 8.x đã cài:

```bash
gradle bootRun
```

Hoặc dùng `./gradlew bootRun` nếu dự án đã có Gradle Wrapper. Bỏ qua log khởi động Spring Boot, **ba dòng do chương trình tự in ra** phải là:

```text
Sau chuyển thành công: A=400, B=200
Lỗi giả lập: Mô phỏng lỗi sau khi cập nhật
Sau lần bị rollback: A=400, B=200
```

Phân tích kết quả:

1. Ban đầu A=500, B=100. Lần thứ nhất trừ 100 rồi cộng 100 và return bình thường; Spring commit, số dư thành 400/200.
2. Lần thứ hai đã trừ 50 và cộng 50 ở trong transaction, nhưng ném `IllegalStateException` trước commit. Đây là `RuntimeException`, nên Spring rollback cả hai câu `UPDATE`. Số dư vẫn 400/200.
3. `catch` nằm ở **bean gọi bên ngoài** và chỉ bắt exception sau khi `transfer` đã thoát qua proxy, vì thế không vô hiệu hóa rollback. Nếu nuốt exception **bên trong** phương thức transaction và trả về bình thường, Spring có thể commit trừ khi transaction đã bị đánh dấu rollback-only.

### Thử biến thể sai để thấy ranh giới bị vỡ

Bỏ `@Transactional` khỏi `TransferService.transfer` rồi chạy lại dự án với H2 khởi tạo mới. Khi mỗi lệnh cập nhật chạy độc lập theo chế độ auto-commit của connection, cả hai `UPDATE` trong lần lỗi có thể đã commit trước khi exception xuất hiện. Kết quả lúc này có thể là A=350, B=250 dù thao tác nghiệp vụ báo lỗi. Đó là bằng chứng rằng exception **tự nó không phải cơ chế rollback các thao tác DB đã commit**.

Biến thể xấu hơn: nếu không có transaction và câu thứ hai lỗi sau khi câu đầu đã commit, A bị trừ mà B chưa được cộng, vi phạm invariant. Ví dụ chạy thật ở trên giữ nguyên cấu trúc Spring để quan sát rõ điểm khác biệt; khi tái thử, luôn khởi tạo DB mới để không dùng trạng thái cũ.

## 6. Những điểm cắt transaction thường gặp

### 6.1. Nên đặt ở service điều phối, không ở controller

Controller nên tập trung vào giao thức, xác thực, parse/validate và trả kết quả. Nếu gọi nhiều repository trực tiếp từ controller mà mỗi repository chạy transaction riêng, toàn bộ use case dễ bị phân mảnh. Một service có tên theo ý định nghiệp vụ diễn đạt rõ ranh giới và tái sử dụng được khi endpoint chuyển thành job hoặc message consumer.

Một repository có thể dùng transaction riêng trong những API độc lập; vấn đề không phải “repository không được có `@Transactional`”, mà là **đừng để nó vô tình tự commit những phần mà use case cần cùng rollback**. Với `REQUIRED`, repository thường tham gia transaction do service mở.

### 6.2. Đừng trùm I/O ngoài DB bằng một transaction dài

Nếu service đã ghi DB rồi giữ connection trong lúc gọi API bên ngoài, có hai nguy cơ đồng thời: transaction giữ tài nguyên/khóa lâu và API bên ngoài **không** thuộc rollback của CSDL. Gửi email thành công rồi DB rollback không “thu hồi” email. Thanh toán thành công rồi DB rollback không tự hoàn tiền.

Có thể ghi dữ liệu nghiệp vụ **và bản ghi outbox** trong một transaction, sau commit dùng worker đọc outbox để phát message; phía nhận cần xử lý trùng/idempotency vì delivery có thể lặp. Với thao tác xuyên dịch vụ cần phối hợp dài hạn, cân nhắc workflow/saga và bước bù trừ; đó không phải một local ACID transaction.

### 6.3. Đồng thời và lock là phần của thiết kế

Trong chuyển tiền, nếu hai request cùng đọc A=100 rồi cùng quyết định rút 80, việc chỉ “đọc → kiểm tra → cập nhật” mà không có cơ chế đồng thời phù hợp có thể dẫn đến lost update hoặc vi phạm điều kiện kinh doanh. Câu `UPDATE ... WHERE balance >= ?` kiểm tra và trừ trên cùng phép cập nhật; `CHECK (balance >= 0)` cung cấp lớp bảo vệ DB. Với domain phức tạp có thể cần optimistic locking bằng version, pessimistic locking hoặc isolation cao hơn. Giao dịch vẫn phải xử lý deadlock/serialization failure và chỉ retry khi thao tác có thể lặp an toàn.

### 6.4. Xử lý lỗi phải tương ứng với ý nghĩa rollback

- Ném `RuntimeException` ra khỏi phương thức `@Transactional` thường yêu cầu rollback mặc định.
- Một checked exception cần quy tắc rollback phù hợp: `@Transactional(rollbackFor = SomeCheckedException.class)` nếu thao tác phải hủy.
- Nếu `try/catch` bắt lỗi và **không rethrow** hoặc đánh dấu rollback-only, Spring có thể coi phương thức thành công và commit. Khi muốn business failure không phát exception, phải quyết định rõ transaction vẫn có thể commit hay cần rollback.
- Một scope `REQUIRED` bên trong đã đánh dấu rollback-only có thể khiến scope ngoài nhận `UnexpectedRollbackException` lúc cố commit; đừng hiểu đó là “Spring tự ý bỏ qua giao dịch”.

### 6.5. Proxy và luồng gọi thực tế

`@Transactional` trên một method chỉ có hiệu lực khi transaction advice thực sự chạy. Trong proxy mode mặc định, trường hợp `this.transfer(...)` gọi từ method khác của cùng bean không đi qua proxy. Tương tự, gọi phương thức trên object tạo bằng `new` mà Spring không quản lý sẽ không có proxy. Cách thực tế là đặt use case ở Spring bean và gọi qua bean được inject; đừng dùng self-invocation để mong đổi propagation. Transaction imperative không tự kéo sang một thread khác.

## 7. Cách quyết định ranh giới: bảng tình huống

| Tình huống | Ranh giới phù hợp | Lý do |
| --- | --- | --- |
| Tạo đơn và các dòng hàng trong cùng CSDL | Một transaction ở `OrderService.placeOrder` | Không có “đơn nửa chừng” |
| Chuyển tiền giữa hai dòng trong cùng CSDL | Một transaction ở `TransferService.transfer` | Ghi nợ/ghi có cần atomicity |
| Đọc trang danh sách không cập nhật dữ liệu | Có thể dùng scope đọc `readOnly` nếu cần consistency/snapshot | Không phải cứ HTTP GET là phải transaction dài |
| Gọi cổng thanh toán và lưu đơn hàng | Chia các bước theo trạng thái, outbox/workflow và idempotency | Local DB transaction không kiểm soát tài nguyên bên ngoài |
| Import một triệu dòng từ file | Giao dịch theo chunk với checkpoint phù hợp | Một transaction khổng lồ dễ giữ lock và log quá lâu |
| Ghi audit ở giao dịch độc lập dù nghiệp vụ thất bại | Chỉ cân nhắc `REQUIRES_NEW` nếu yêu cầu audit rõ ràng | Giao dịch audit có thể commit khi transaction ngoài rollback; phải tính connection pool |

Một nguyên tắc thực dụng: **mở transaction muộn nhất có thể nhưng trước thay đổi cần nhất quán; kết thúc sớm nhất có thể sau thay đổi cuối cùng cần atomic commit**. Không chia giữa các bước mà invariant yêu cầu phải cùng thành công.

## 8. Kiểm thử đúng ranh giới

Đừng chỉ kiểm tra “service ném lỗi”; cần kiểm tra **trạng thái DB sau lỗi**. Với ví dụ chuyển tiền:

1. Chuẩn bị hai tài khoản với số dư xác định, gọi service qua Spring bean thật.
2. Ca thành công: assert số dư nguồn giảm và đích tăng đúng lượng; tổng không đổi.
3. Ca lỗi sau khi đã ghi: assert exception và assert **cả hai số dư không đổi**.
4. Ca không đủ tiền: assert không cập nhật bất cứ tài khoản nào.
5. Ca nhiều request đồng thời: assert không có số dư âm, không mất tiền; nếu CSDL báo deadlock/conflict thì kiểm tra retry policy phù hợp.
6. Nếu đổi propagation, transaction manager hoặc thêm I/O ngoài DB, bổ sung kiểm thử theo những ranh giới mới.

**Lưu ý khi viết test bằng Spring:** test method gắn `@Transactional` thường được Spring TestContext tự rollback sau mỗi test. Điều đó hữu ích để cô lập dữ liệu nhưng có thể che mất sai sót trong thiết kế khi chỉ quan sát dữ liệu **bên trong** transaction của test. Với bài kiểm thử commit/rollback thực tế, hãy chủ động kiểm soát transaction của test và đọc trạng thái sau khi scope service kết thúc; đừng coi việc test tự rollback là bằng chứng service rollback đúng.

## 9. Checklist thiết kế và lỗi thường gặp

Trước khi đánh dấu `@Transactional`, tự trả lời:

- Kết quả nghiệp vụ duy nhất cần đảm bảo là gì? Invariant nào có thể bị hỏng nếu một bước commit riêng?
- Những thay đổi có thực sự thuộc **cùng tài nguyên giao dịch** không? Có email, HTTP, queue hoặc DB khác nằm ngoài không?
- Method nào thể hiện một use case và được gọi qua Spring proxy? Có self-invocation hoặc thread mới không?
- Có ném exception nào cần rollback nhưng mặc định không rollback (checked exception hoặc lỗi bị nuốt) không?
- Có khóa, constraint, version hoặc phép cập nhật có điều kiện để bảo vệ invariant trước truy cập đồng thời không?
- Transaction có giữ tài nguyên trong lúc chờ network, sleep, tính toán nặng hoặc tương tác người dùng không?
- Đã có test khiến lỗi xảy ra **giữa các bước ghi**, rồi xác nhận readback trạng thái DB sau rollback chưa?

Các nhầm lẫn cần tránh: “mỗi truy vấn là một giao dịch”, “mọi request là một giao dịch”, “`@Transactional` bảo đảm không có race condition”, “gọi API ngoài cũng rollback”, “bắt exception rồi return thì vẫn tự rollback”, và “đặt annotation ở private method hoặc tự gọi trong cùng bean luôn có tác dụng”.

## 10. Tự kiểm tra

**Câu 1.** Trong một use case lưu đơn hàng và các dòng hàng cùng CSDL, có nên cho từng repository tự commit độc lập? **Trả lời:** Không nếu invariant yêu cầu cùng thành công; đặt transaction bao quanh use case ở service.

**Câu 2.** Service đã trừ kho trong DB, gửi email thành công, rồi phát sinh exception. `@Transactional` có thu hồi email không? **Trả lời:** Không; DB có thể rollback nhưng email là side effect ngoài DB. Cần chọn thời điểm gửi phù hợp, event after-commit nếu chấp nhận mức tin cậy đó, hoặc transactional outbox nếu cần phát đáng tin cậy.

**Câu 3.** Gọi `this.inner()` từ `outer()`, trong đó `inner()` có `@Transactional(propagation = REQUIRES_NEW)`, liệu chắc chắn có transaction mới không? **Trả lời:** Không với proxy mode mặc định; lời gọi nội bộ không bị proxy chặn.

**Câu 4.** Một transaction có thể chống mọi lost update chỉ vì nó bao quanh nhiều câu SQL không? **Trả lời:** Không. Phải xem isolation, pattern đọc/sửa/ghi, ràng buộc CSDL, locking hoặc optimistic version.

**Câu 5.** Thấy exception trong service nhưng số dư vẫn đổi sau đó, kiểm tra gì đầu tiên? **Trả lời:** Service có được gọi qua Spring proxy không, có transaction manager phù hợp không, exception có thoát qua interceptor và thỏa rollback rule không, repository có cùng transaction không, hay DB đã auto-commit trước đó?

## Tài liệu đối chiếu

- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Boot — Database Initialization: https://docs.spring.io/spring-boot/how-to/data-initialization.html

**Ghi nhớ:** Một đơn vị công việc nghiệp vụ xác định **điều gì phải đúng sau khi hoàn tất**. Ranh giới transaction là quyết định kỹ thuật để hiện thực phần nguyên tử trên các tài nguyên được quản lý. Chọn ranh giới theo invariant và tài nguyên thật, rồi dùng kiểm thử rollback để chứng minh.