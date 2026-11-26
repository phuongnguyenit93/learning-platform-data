# Chọn dữ liệu kiểm thử và dọn trạng thái sau mỗi ca

Một ca kiểm thử tích hợp Spring Web Flow có thể vượt qua khi chạy riêng nhưng thất bại trong cả bộ test. Nguyên nhân thường nằm ở trạng thái dùng chung: bản nháp còn trong database, flow execution còn trong session, cookie đăng nhập được tái sử dụng hoặc stub dịch vụ vẫn giữ cấu hình lỗi của ca trước.

Trong chương **Kiểm thử tích hợp** của module **SPRING_WEB_FLOW**, bài này trình bày cách chọn dữ liệu có ý nghĩa và quản lý toàn bộ vòng đời của nó. Mục tiêu là kiểm tra hành trình qua state, event, transition và subflow với form binding, validation, scope và phiên thực tế, đồng thời giữ cho mỗi ca độc lập và có thể chạy lại.

## 1. Bắt đầu bằng phạm vi trạng thái, không chỉ bằng một bản ghi

Một hành trình nhập và xác nhận đơn có thể chạm tới nhiều nơi lưu trạng thái:

| Nơi giữ trạng thái | Ví dụ | Hướng cô lập và dọn |
| --- | --- | --- |
| Database | Tài khoản, bản nháp, đơn, chi tiết đơn | Tạo dữ liệu thuộc riêng ca test; xóa theo quan hệ sở hữu |
| HTTP session | Đăng nhập và repository flow theo cấu hình | Session mới cho mỗi ca; vô hiệu hóa session khi kết thúc |
| Flow execution | Flow scope, view scope, snapshot | Không dùng lại execution key giữa các ca |
| Conversation/subflow | Dữ liệu chia sẻ qua hành trình cha/con | Tạo execution mới, kiểm tra output và vòng đời tương ứng |
| Client | Cookie, local storage, URL execution cũ | Client hoặc browser context mới; bỏ dữ liệu phiên cũ |
| Cache hoặc singleton có trạng thái | Kết quả tồn kho, giá, bộ đếm | Dùng khóa riêng hoặc reset đúng vùng mà test sở hữu |
| Stub/mock dịch vụ ngoài | Kịch bản timeout, lịch sử request | Xóa kịch bản và lịch sử theo phạm vi riêng của ca |
| Tác vụ nền, message, tệp | Outbox, email giả, file upload | Định danh riêng; chờ kết thúc hoặc hủy có kiểm soát rồi dọn |

Xóa bản nháp trong database không làm biến mất DTO đang được giữ trong `flowScope`. Ngược lại, kết thúc flow không xóa đơn hàng đã được commit. Hai loại trạng thái cần được quản lý riêng.

Với cấu hình repository dựa trên phiên thông thường, execution được gắn với phiên người dùng; các giới hạn execution và snapshot cũng có thể ảnh hưởng đến test tạo nhiều flow. Cần đối chiếu cấu hình thật thay vì giả định mọi repository có cùng cơ chế lưu trữ. Xem phần Flow Execution Repository trong [Spring Web Flow Reference Guide](https://docs.spring.io/spring-webflow/docs/current/reference/index.html).

## 2. Chọn dữ liệu tối thiểu nhưng đủ chứng minh hành vi

Một fixture tốt chứa đúng những dữ liệu cần để đi qua nhánh đang kiểm tra. Không cần nạp cả một bản sao lớn của dữ liệu vận hành chỉ để kiểm tra nút xác nhận.

Ví dụ, với flow đặt hàng, dữ liệu có thể gồm:

- Một tài khoản sở hữu bản nháp.
- Một bản nháp có số lượng và trạng thái xác định.
- Một sản phẩm hoặc bảng giá nền đã được tạo bằng migration/seed ổn định.
- Phản hồi dịch vụ tồn kho hoặc thanh toán tương ứng với kịch bản.

Dữ liệu dùng chung chỉ nên là dữ liệu nền ít thay đổi và không bị test sửa, chẳng hạn mã quốc gia. Bản nháp, đơn và tồn kho mà test thay đổi nên thuộc riêng từng ca hoặc một môi trường được cô lập rõ ràng.

### Ma trận dữ liệu theo loại kịch bản

| Kịch bản | Dữ liệu được chọn | Điều cần quan sát |
| --- | --- | --- |
| Thành công | Bản nháp hợp lệ, sản phẩm có thể đặt | Flow hoàn tất; có đúng đơn cần tạo |
| Validation | Số lượng bằng 0 hoặc trường bắt buộc trống | Chưa tạo đơn; form và thông báo phù hợp |
| Binding | Chuỗi không chuyển được sang số | Giá trị nhập bị từ chối vẫn hiển thị để sửa |
| Quay lại | Bản nháp đã nhập, sau đó sửa một thuộc tính | Lần xác nhận dùng giá trị mới |
| Hủy | Bản nháp đang ở màn hình cho phép hủy | Không phát sinh tác dụng phụ ngoài hợp đồng hủy |
| Từ chối nghiệp vụ | Điều kiện tồn kho/giá không còn thỏa | Không báo thành công; còn dữ liệu cần sửa |
| Chưa rõ kết quả | Khóa yêu cầu ổn định, dịch vụ trả timeout phù hợp | Giữ mã đối chiếu; không tự gửi trùng |
| Khác chủ sở hữu | Hai tài khoản và hai bản nháp riêng | Không truy cập hoặc cập nhật nhầm bản nháp |
| Hết phiên | Bản nháp và session cũ đã được tạo | Không tiếp tục âm thầm bằng execution cũ |

Đối với binding, phải đưa giá trị thô vào request hoặc thao tác trên form. Gán trực tiếp một số nguyên vào DTO rồi gửi event chỉ kiểm tra hành vi với model đã được chuyển đổi, không kiểm tra bộ chuyển đổi dữ liệu.

Với `LANG=vi`, nên có trường hợp giao diện dùng thông báo tiếng Việt và định dạng theo locale đã cấu hình. Không mặc định dấu phân cách số hoặc định dạng ngày chỉ vì nội dung bài học là tiếng Việt; đó là hợp đồng của formatter và locale trong ứng dụng.

## 3. Giữ dữ liệu xác định, chỉ ngẫu nhiên hóa định danh

Có thể tạo UUID riêng cho tài khoản và bản nháp của mỗi ca. Nội dung có ý nghĩa nghiệp vụ nên cố định để thất bại có thể giải thích được.

```text
customerId: UUID riêng của ca
 draftId: UUID riêng của ca
 email: it-<customerId>@example.invalid
 quantity: 2
 status: EDITING
 thời điểm nghiệp vụ: 2026-11-01T03:00:00Z, nếu kịch bản cần kiểm tra thời gian
```

Số lượng ngẫu nhiên, ngày hết hạn lấy trực tiếp từ đồng hồ thật hoặc tên bản ghi được chọn tùy ý dễ làm test chập chờn. Với logic phụ thuộc thời gian, ưu tiên đưa `Clock` có thể điều khiển vào dịch vụ và cố định nó trong test phù hợp.

Nếu kiểm tra báo giá hết hạn, chọn dữ liệu thể hiện rõ hai phía của ranh giới. Chẳng hạn, với quy tắc hết hạn tại `expiresAt`, kiểm tra thời điểm trước hạn và đúng thời điểm hết hạn theo hợp đồng, thay vì chờ test ngủ đến lúc giá hết hạn.

### Khóa chống gửi trùng phải có vòng đời riêng

Định danh ca test và idempotency key không nhất thiết là một giá trị. Một ca có thể mô phỏng hai ý định đặt hàng, mỗi ý định có khóa riêng. Ngược lại, các lần thử lại cùng một ý định phải dùng cùng khóa để kiểm tra chống gửi trùng.

Không tạo khóa mới cho mọi lần submit trong test phục hồi rồi kết luận cơ chế idempotency đã đúng. Dữ liệu của test phải bảo toàn đúng quan hệ giữa yêu cầu ban đầu và yêu cầu gửi lại.

### Không phụ thuộc vào ID sinh tuần tự cụ thể

Đừng kỳ vọng đơn mới luôn có ID bằng 1 hoặc reset sequence chỉ để assertion đó qua. Hãy lấy ID do fixture hoặc dịch vụ trả về và truy vấn theo chủ sở hữu/khóa nghiệp vụ của ca.

Tương tự, tránh `select count(*) from purchase_order` trên database dùng chung cho nhiều ca. Câu hỏi đúng thường là “có bao nhiêu đơn thuộc tài khoản hoặc yêu cầu của ca này?”.

## 4. Chọn chiến lược transaction theo cách test gọi ứng dụng

Test tích hợp có thể chạy trong nhiều kiểu môi trường, với ranh giới transaction khác nhau.

| Kiểu test | Giả định có thể dùng | Điểm cần kiểm chứng |
| --- | --- | --- |
| Gọi dịch vụ đồng bộ trong test-managed transaction | Thao tác tham gia transaction có thể rollback cuối ca | Đúng transaction manager, thread và propagation |
| MockMvc đồng bộ | Request thường được xử lý trong luồng gọi test | Có async dispatch, transaction độc lập hoặc nhiều datasource không? |
| HTTP tới server chạy thật | Client và server có thread/transaction riêng | Cần seed đã commit và cleanup dữ liệu server đã commit |
| Tác vụ nền hoặc message consumer | Công việc có thể tiếp tục ngoài lời gọi test | Phải quản lý cả hoàn tất công việc và dữ liệu phát sinh |

Spring gắn test-managed transaction vào thread. Việc chuyển thread hoặc dùng propagation độc lập có thể khiến thao tác không thuộc transaction mà test sẽ rollback. Đặc biệt, timeout kiểu chạy test ở thread khác có thể làm sai giả định này. Xem [Transaction Management trong Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html).

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc `DEFINED_PORT`, request HTTP được server xử lý ở thread khác; transaction phía server không tự rollback theo transaction của phương thức test. Đây là giới hạn được nêu trong [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html).

### Hai lỗi đối xứng thường gặp

**Seed chưa commit:** test chèn bản nháp trong transaction của nó, rồi gọi server thật. Request phía server có thể không thấy bản nháp vì transaction seed chưa commit.

**Cleanup tưởng đã xong nhưng bị rollback:** teardown xóa đơn trong transaction của test, rồi framework rollback transaction đó. Dữ liệu server đã commit có thể còn lại vì thao tác xóa chưa được commit độc lập.

Đối với ca cần quan sát dữ liệu đã commit, một chiến lược dễ hiểu là: seed bằng transaction riêng đã commit, chạy hành trình, assert dữ liệu và dọn bằng transaction riêng đã commit. Không trộn chiến lược này với kỳ vọng “mọi thứ sẽ tự rollback” trong cùng một ca.

## 5. Ví dụ fixture có quyền sở hữu rõ ràng

Ví dụ sau minh họa một schema PostgreSQL của ứng dụng kiểm thử:

| Bảng | Các cột liên quan |
| --- | --- |
| `customer_account` | `id` UUID, `email` |
| `order_draft` | `id` UUID, `customer_id`, `quantity`, `status` |
| `purchase_order` | `id`, `customer_id` |
| `purchase_order_line` | `id`, `order_id` |

Tên bảng và quan hệ là ví dụ, không phải schema do Spring Web Flow cung cấp. Mọi đơn phát sinh trong ca được giả định gắn với `customerId` của fixture; nếu hệ thống tạo thêm bảng, phải đưa chúng vào hợp đồng cleanup.

Đoạn Java dùng text block, phù hợp với Java 17 trở lên. `JdbcTemplate` và `PlatformTransactionManager` phải cùng quản lý datasource kiểm thử cần seed/dọn. Với nhiều datasource, cần chọn bean bằng qualifier thích hợp.

```java
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public final class CheckoutFixture implements AutoCloseable {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate independentTx;
    private final UUID customerId = UUID.randomUUID();
    private final UUID draftId = UUID.randomUUID();

    public CheckoutFixture(JdbcTemplate jdbc,
                           PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.independentTx = new TransactionTemplate(transactionManager);
        this.independentTx.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public UUID customerId() {
        return customerId;
    }

    public UUID draftId() {
        return draftId;
    }

    public void seed() {
        independentTx.executeWithoutResult(status -> {
            jdbc.update("""
                    insert into customer_account(id, email)
                    values (?, ?)
                    """, customerId, "it-" + customerId + "@example.invalid");

            jdbc.update("""
                    insert into order_draft(id, customer_id, quantity, status)
                    values (?, ?, ?, ?)
                    """, draftId, customerId, 2, "EDITING");
        });
    }

    public int countOrders() {
        Integer count = jdbc.queryForObject("""
                select count(*) from purchase_order where customer_id = ?
                """, Integer.class, customerId);
        return count == null ? 0 : count;
    }

    @Override
    public void close() {
        independentTx.executeWithoutResult(status -> {
            jdbc.update("""
                    delete from purchase_order_line
                    where order_id in (
                        select id from purchase_order where customer_id = ?
                    )
                    """, customerId);

            jdbc.update("delete from purchase_order where customer_id = ?",
                    customerId);
            jdbc.update("delete from order_draft where customer_id = ?",
                    customerId);
            jdbc.update("delete from customer_account where id = ?",
                    customerId);
        });
    }
}
```

`TransactionTemplate` quản lý vòng đời transaction của callback và cho phép cấu hình propagation; xem [API TransactionTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html). Ở đây seed thành công được commit trước khi trả về; cleanup cũng được commit độc lập khi callback hoàn tất.

Không đặt một transaction bao quanh cả hành trình HTTP rồi dùng `REQUIRES_NEW` như cách chữa mọi vấn đề. Transaction dài có thể giữ khóa và làm thao tác độc lập bị chặn. Fixture mẫu được thiết kế cho test không có outer transaction bao toàn bộ phương thức.

### Các thuộc tính quan trọng của cleanup

- Xóa bảng con trước bảng cha theo quan hệ khóa ngoại.
- Chỉ xóa dữ liệu thuộc tài khoản riêng của ca.
- Có thể gọi lại `close()` sau khi dữ liệu đã mất; câu lệnh `DELETE` khớp 0 dòng vẫn hợp lệ.
- Không nuốt exception SQL: cleanup thất bại phải xuất hiện trong kết quả test.
- Seed các dòng trong một transaction, nên lỗi giữa chừng làm rollback phần seed của callback.

`countOrders()` chỉ có ý nghĩa khi đọc được trạng thái cần quan sát. Nếu bên ngoài đang giữ một transaction với snapshot cũ hoặc chưa flush ORM, hãy chọn ranh giới đọc phù hợp; đừng mặc định mọi truy vấn đều nhìn thấy kết quả commit mới nhất.

Fixture này chưa quản lý cache, message, outbox hoặc job nền. Không dùng nó để kết luận rằng mọi trạng thái của ứng dụng đã được dọn.

## 6. Ghép fixture với vòng đời session trong test tích hợp MVC

Một test Web Flow cần cấu hình thật của handler mapping, handler adapter, flow registry, executor và view infrastructure tương ứng. MockMvc dựng từ `WebApplicationContext` phù hợp để kiểm tra cấu hình MVC đã nạp; chỉ dựng một controller đơn lẻ không tự mang theo cấu hình Web Flow. Xem [Configuring MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/setup.html).

Khung ví dụ dưới dùng JUnit Jupiter. `CheckoutIntegrationTestConfig` là cấu hình do ứng dụng cung cấp, gồm MVC/Web Flow và datasource test; nó không phải một lớp có sẵn trong Spring.

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.web.context.WebApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringJUnitWebConfig(CheckoutIntegrationTestConfig.class)
@ActiveProfiles("test")
class CheckoutIntegrationTests {
    @Autowired WebApplicationContext applicationContext;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;

    private CheckoutFixture fixture;
    private MockHttpSession session;
    private MockMvc mvc;

    @BeforeEach
    void prepare() {
        fixture = new CheckoutFixture(jdbc, transactionManager);
        fixture.seed();
        session = new MockHttpSession(applicationContext.getServletContext());
        mvc = MockMvcBuilders.webAppContextSetup(applicationContext).build();
    }

    @Test
    void startsCheckoutFromOwnDraft() throws Exception {
        // Giả định hợp đồng của ứng dụng: khởi động flow trả redirect
        // tới execution URL và việc xác thực đã được cấu hình phù hợp.
        MvcResult result = mvc.perform(get("/orders/checkout")
                        .session(session)
                        .param("draftId", fixture.draftId().toString()))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String executionUrl = result.getResponse().getRedirectedUrl();
        assertNotNull(executionUrl);
        assertTrue(executionUrl.contains("execution="));
        assertEquals(0, fixture.countOrders());
    }

    @AfterEach
    void cleanUp() {
        try {
            if (session != null && !session.isInvalid()) {
                session.invalidate();
            }
        } finally {
            if (fixture != null) {
                fixture.close();
            }
        }
    }
}
```

Đây là khung minh họa cho ứng dụng có đường dẫn và quy ước redirect nêu trong comment. Nếu ứng dụng render trực tiếp, dùng URL rewrite khác hoặc yêu cầu đăng nhập, phải thay phần request/assert theo hợp đồng thật. Không coi chuỗi `execution=` là assertion đủ mạnh cho toàn bộ màn hình.

Trong các bước tiếp theo, lấy URL/key từ response thực tế và giữ cùng session trong phạm vi ca; không viết cứng `e1s1`. Nếu xác thực làm thay session hoặc response tạo session mới, test cần theo dõi session đang được sử dụng để teardown dọn đúng đối tượng.

MockMvc cần được gắn filter và tích hợp bảo mật tương ứng nếu phạm vi test bao gồm Spring Security. Không bỏ qua CSRF hoặc đăng nhập rồi coi đây là kiểm thử đầy đủ của hành trình được bảo vệ.

### Vì sao dọn session trước database trong ví dụ?

Ví dụ giả định request đồng bộ đã hoàn tất và không có công việc nền đang chạy. Vô hiệu hóa session giúp chấm dứt việc tái sử dụng trạng thái phiên trước khi xóa dữ liệu sở hữu của ca. `finally` bảo đảm cleanup database vẫn được thử nếu bước vô hiệu hóa session phát sinh lỗi.

`MockHttpSession.invalidate()` vô hiệu hóa session; API và các phương thức kiểm tra trạng thái được mô tả tại [MockHttpSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mock/web/MockHttpSession.html). Nếu repository flow hoặc session store của ứng dụng dùng kho ngoài, cần kiểm tra cơ chế hết hạn/xóa tại kho đó; một mock session không chứng minh hành vi của Redis hay servlet container thật.

Với listener khi hủy session hoặc dữ liệu phiên lưu ngoài, thứ tự dọn có thể phải điều chỉnh theo hợp đồng của ứng dụng. Nguyên tắc là không để công việc còn hoạt động tiếp tục ghi vào dữ liệu vừa được xóa.

## 7. Với HTTP thật và trình duyệt, tạo phạm vi client riêng

Khi chạy server thật, client không có quyền gọi trực tiếp `invalidate()` trên session server như với `MockHttpSession`. Cần phân biệt:

- Xóa cookie phía client ngăn ca sau dùng lại cookie đó, nhưng không tự xóa ngay session phía server.
- Logout chỉ hủy session nếu ứng dụng được cấu hình theo hợp đồng đó; cần xác minh hiệu lực thật.
- Kết thúc flow dọn trạng thái execution theo cấu hình, nhưng có thể vẫn giữ phiên đăng nhập và dữ liệu nghiệp vụ.

Dùng client/cookie jar hoặc browser context riêng cho mỗi ca. Nếu dùng một browser context để kiểm tra nhiều tab trong cùng session, đó phải là chủ đích của ca, không phải hệ quả của fixture dùng chung.

Đối với server test cô lập, có thể quản lý vòng đời session bằng cơ chế test đã thiết kế, timeout hoặc đóng môi trường theo phạm vi. Không chỉ bỏ cookie rồi kết luận repository phía server đã sạch.

Một execution key là định danh của lần thực thi, không phải một dữ liệu mẫu tái sử dụng cho mọi test. Khi kiểm tra execution hết hiệu lực, hãy tạo key trong chính ca đó, làm hết hiệu lực theo kịch bản rồi kiểm tra phản hồi.

## 8. Chọn giữa rollback, SQL script và môi trường dùng một lần

Không có một kỹ thuật dọn phù hợp với mọi cấp kiểm thử.

| Kỹ thuật | Phù hợp khi | Giới hạn cần nhớ |
| --- | --- | --- |
| Rollback test-managed transaction | Kiểm tra đồng bộ có cùng ranh giới transaction | Không bao phủ tự động server thread, job hoặc transaction độc lập |
| Fixture có ID riêng và cleanup có điều kiện | HTTP/server commit thật, có chạy song song | Phải biết đầy đủ dữ liệu phát sinh và quan hệ sở hữu |
| `@Sql` trước/sau ca | Seed cố định, dễ mô tả bằng SQL | Cần chọn đúng transaction mode và thứ tự listener |
| Schema/database riêng theo worker | Nhiều ca thay đổi dữ liệu lớn | Cần quản lý migration, chi phí tạo và vòng đời worker |
| Database/container dùng một lần | Cần môi trường cô lập rõ ràng | Dùng chung một instance qua nhiều ca vẫn cần cô lập giữa các ca |

Có thể dùng `@Sql` với script setup trước phương thức test và script cleanup sau phương thức test. Khi cần script chạy trong transaction riêng, xem `@SqlConfig(transactionMode = ISOLATED)` và cấu hình transaction manager/datasource. Không coi việc có `AFTER_TEST_METHOD` là đủ bảo đảm mọi thay đổi của cleanup đã commit theo đúng ý muốn. Xem [Executing SQL Scripts trong Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html).

Script tĩnh xóa toàn bộ bảng chỉ phù hợp khi database/schema thực sự thuộc riêng phạm vi đang dọn và không có ca khác truy cập. Với database dùng chung, ưu tiên điều kiện theo ID sở hữu hoặc tách schema, tránh cleanup toàn cục gây lỗi cho ca chạy song song.

### `@DirtiesContext` không phải lệnh xóa dữ liệu

`@DirtiesContext` loại `ApplicationContext` bị thay đổi khỏi cache và đóng nó để lần sau dựng lại. Nó không có nghĩa tự xóa database ngoài, session store ngoài hoặc message queue. Nên dùng khi test đã làm bẩn trạng thái context/singleton mà không có cách reset phù hợp, theo [tài liệu @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html).

Không đóng rồi tạo lại toàn bộ Spring context cho mỗi ca chỉ để bù cho fixture thiếu quyền sở hữu. Cách đó vừa tốn thời gian vừa có thể để nguyên dữ liệu đã commit ở kho ngoài.

## 9. Dọn trạng thái bất đồng bộ và xử lý ca thất bại

Thứ tự phổ biến cho một ca có tác vụ nền là:

1. Ghi nhận bằng chứng cần thiết của ca: response, mã đối chiếu và dữ liệu liên quan.
2. Chờ công việc thuộc ca đạt trạng thái hoàn tất, hoặc hủy theo cơ chế hỗ trợ của ứng dụng.
3. Chấm dứt quyền tái sử dụng session/execution theo cấu hình.
4. Dọn tài nguyên ngoài, cache và dữ liệu theo quan hệ phụ thuộc.
5. Kiểm tra điều kiện sạch phù hợp với phạm vi của ca.

Không dùng `Thread.sleep(5000)` làm bằng chứng rằng tất cả công việc đã kết thúc. Hãy chờ một điều kiện quan sát được với timeout hữu hạn, chẳng hạn trạng thái job, số message đã xử lý hoặc sự kiện hoàn tất.

Nếu job vẫn có thể chạy sau cleanup, nó có thể tạo lại dữ liệu vừa xóa hoặc gặp lỗi vì bản ghi cha đã mất. Đó là lỗi quản lý vòng đời công việc, không chỉ là câu SQL xóa sai.

### Assertion thất bại vẫn phải được dọn

Teardown cần chạy khi assertion thất bại. Chỉ in log rồi bỏ qua lỗi cleanup sẽ làm ca sau khó chẩn đoán. Framework kiểm thử phải báo được lỗi gốc và lỗi teardown; khi tự viết wrapper, giữ lỗi cleanup như thông tin bổ sung thay vì làm mất lỗi ban đầu.

Nếu cần giữ bằng chứng, chụp response, ảnh màn hình hoặc trích xuất dữ liệu đã lọc trước khi dọn. Không để database bẩn như một cách lưu bằng chứng mặc định.

`@AfterEach` không thể bảo đảm chạy khi process bị kill hoặc máy mất điện. Với môi trường dùng lâu, cần cách nhận diện tài nguyên test đã bỏ lại và dọn theo phạm vi/tuổi tài nguyên được quy định. UUID riêng giúp tránh va chạm; nó không tự giải phóng dữ liệu tồn dư.

## 10. Kiểm tra xem fixture đã đủ độc lập chưa

Các dấu hiệu sau cho thấy cần xem lại thiết kế dữ liệu hoặc cleanup:

| Dấu hiệu | Nguyên nhân cần điều tra |
| --- | --- |
| Test chỉ qua khi chạy sau một ca khác | Đang phụ thuộc seed hoặc đăng nhập của ca trước |
| Chạy riêng qua, chạy cả bộ lỗi unique key | ID/email dùng chung hoặc dữ liệu cũ chưa được dọn |
| Request không thấy bản nháp vừa seed | Chưa commit, sai datasource hoặc sai tenant |
| Cleanup báo vi phạm khóa ngoại | Thiếu bảng con hoặc còn công việc đang tạo dữ liệu |
| Test nhìn thấy model cũ | Session/execution/client đã được tái sử dụng |
| Tổng số đơn thay đổi bất thường | Query đếm toàn cục hoặc có tác vụ nền chưa hoàn tất |
| Lỗi khi chạy song song | Reset toàn cục, cache key chung hoặc stub dùng chung |
| Hủy flow nhưng vẫn còn đơn | Nhầm vòng đời execution với dữ liệu nghiệp vụ đã commit |

Khi triển khai bộ test, nên xác minh các tính chất sau trong phạm vi phù hợp: chạy riêng được, chạy lại được, không phụ thuộc thứ tự và không xóa dữ liệu của ca khác. Chạy song song chỉ có ý nghĩa khi datasource, session, cache và test double đã có chiến lược cô lập tương ứng.

## 11. Bài tập áp dụng

Thiết kế fixture cho hai ca của cùng flow đặt hàng:

1. Ca thứ nhất đi đến xác nhận thành công, kiểm tra đúng một đơn thuộc tài khoản của ca, rồi dọn session và các bản ghi phát sinh.
2. Ca thứ hai sửa số lượng, quay lại màn hình nhập rồi hủy; kiểm tra không có đơn được tạo và dữ liệu của ca thứ nhất không được dùng lại.

Sau đó mở rộng bằng một ca hai người dùng: người A khởi động flow với bản nháp của người B. Dữ liệu cần gồm hai chủ sở hữu và hai phạm vi session rõ ràng; teardown phải quản lý cả hai, kể cả khi ứng dụng từ chối request ngay từ đầu.

Khi đánh giá thiết kế, hãy viết ra ba câu trả lời: **ai sở hữu từng dữ liệu, nó phải tồn tại đến lúc nào và thành phần nào có trách nhiệm dọn nó**. Ba câu trả lời này giúp dữ liệu kiểm thử phục vụ đúng hành vi cần kiểm tra, đồng thời giữ các ca tích hợp Spring Web Flow độc lập và có thể tái lập.