# JUnit Jupiter `@Nested` để nhóm các tình huống kiểm thử liên quan

Khi một hành vi có nhiều bối cảnh, danh sách `@Test` phẳng với các tên như `testCase1`, `testCase2` khó cho biết hệ thống đã được kiểm tra ở những trạng thái nào. JUnit Jupiter cung cấp annotation **`@Nested`** để đặt những kiểm thử cùng bối cảnh trong một lớp con, tạo cây có nghĩa: “Tài khoản hoạt động” → “Gói BASIC” → “Không được mở tài liệu trả phí”.

Bài học này giải thích cách tổ chức test bằng `@Nested`, vòng đời của setup/teardown theo từng cấp, phạm vi trạng thái và cách kết hợp với Spring Boot. Ví dụ chính là **Java 17+ và JUnit Jupiter chạy được**, với các assertion thực sự. `@Nested` là tính năng của JUnit Jupiter, không phải annotation riêng của Spring Boot.

## 1. Khái niệm và cú pháp nền tảng

`@Nested` (import `org.junit.jupiter.api.Nested`) đánh dấu **inner class không `static`** nằm trong một test class. JUnit Jupiter khám phá các phép kiểm thử trong đó, tạo cấu trúc phân cấp và áp dụng các lifecycle callbacks của các lớp bao ngoài. Một nested class lại có thể chứa nested class khác.

```java
class LoginPolicyTest {
    @Nested
    class WhenUserIsActive {
        @Test
        void allowsLoginWithValidCredentials() {
            // Ví dụ về vị trí của assertion cho bối cảnh này.
        }
    }

    @Nested
    class WhenUserIsLocked {
        @Test
        void rejectsLogin() {
            // Ví dụ cấu trúc, chưa có assertion và chưa chạy độc lập.
        }
    }
}
```

Đoạn này minh họa **cấu trúc**, không phải bài test hoàn chỉnh. Chỉ có `@Nested` không làm test hữu ích hơn; cần dữ liệu đầu vào, hành động và assertion chứng minh đúng hành vi.

| Annotation | Ý nghĩa |
|---|---|
| `@Test` | Đánh dấu một phương thức test |
| `@Nested` | Biểu diễn một nhóm bối cảnh ở cấp lớp inner |
| `@DisplayName` | Đặt tên nhóm/test rõ ràng trên IDE và báo cáo |
| `@BeforeEach` | Setup trước từng phương thức test ở cấp đó hoặc cấp con |
| `@AfterEach` | Cleanup sau mỗi phương thức test, từ cấp trong ra ngoài |
| `@BeforeAll` / `@AfterAll` | Setup/cleanup một lần theo vòng đời của cấp test tương ứng |
| `@TestInstance` | Quy định tạo instance test theo `PER_METHOD` hay `PER_CLASS` |
| `@ParameterizedTest` | Chạy cùng logic kiểm tra với nhiều bộ dữ liệu, có thể nằm trong `@Nested` |

Các trường hợp nên dùng `@Nested`: một rule cần xác nhận ở các trạng thái “trước/sau”, ở các vai trò “khách/user/admin”, hoặc ở các nhóm “request hợp lệ/request không hợp lệ”. Khi chỉ có 2–3 test đơn giản không có setup hoặc bối cảnh chung, giữ test phẳng thường sáng sủa hơn. **Nhóm theo điều kiện ảnh hưởng đến kết quả**, tránh nhóm theo nhãn chung chung như “PositiveTests” nếu không giải thích được điều kiện.

## 2. Ví dụ hoàn chỉnh: chính sách đọc tài liệu

Giả sử hệ thống quản lý tài liệu có quy tắc:

1. Nếu tài khoản **không hoạt động**, không được mở tài liệu nào.
2. Nếu tài khoản **hoạt động**, gói `BASIC` đọc được tài liệu miễn phí nhưng không được mở tài liệu premium.
3. Nếu tài khoản **hoạt động**, gói `PREMIUM` đọc được cả hai loại tài liệu.
4. Nếu `Plan` là `null`, từ chối rõ ràng bằng exception.

Những quy tắc này hình thành hai cấp bối cảnh: **trạng thái tài khoản** và **loại gói**. Trong mỗi bối cảnh, test xác minh quyền truy cập vào từng loại tài liệu.

### 2.1. Lớp production

File **`src/main/java/com/example/library/DocumentAccessPolicy.java`**:

```java
package com.example.library;

import java.util.Objects;

public final class DocumentAccessPolicy {
    public enum Plan {
        BASIC, PREMIUM
    }

    public boolean canAccess(Plan plan, boolean accountActive,
                             boolean premiumDocument) {
        Objects.requireNonNull(plan, "plan");
        return accountActive && (!premiumDocument || plan == Plan.PREMIUM);
    }
}
```

`Objects.requireNonNull` từ chối `null` bằng `NullPointerException`; với tài khoản không hoạt động, kết quả là `false`; với tài khoản hoạt động, tài liệu không premium được phép, còn tài liệu premium cần `Plan.PREMIUM`.

### 2.2. Test class sử dụng `@Nested` ở hai cấp

File **`src/test/java/com/example/library/DocumentAccessPolicyTest.java`**:

```java
package com.example.library;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentAccessPolicyTest {
    private DocumentAccessPolicy policy;
    private boolean active;
    private DocumentAccessPolicy.Plan plan;

    @BeforeEach
    void createNewPolicy() {
        policy = new DocumentAccessPolicy();
    }

    @Nested
    @DisplayName("Khi tài khoản hoạt động")
    class ActiveAccount {
        @BeforeEach
        void enableAccount() {
            active = true;
        }

        @Nested
        @DisplayName("Và gói là BASIC")
        class BasicPlan {
            @BeforeEach
            void selectPlan() {
                plan = DocumentAccessPolicy.Plan.BASIC;
            }

            @Test
            @DisplayName("Được đọc tài liệu miễn phí")
            void allowsFreeDocument() {
                assertTrue(policy.canAccess(plan, active, false));
            }

            @Test
            @DisplayName("Bị từ chối tài liệu premium")
            void deniesPremiumDocument() {
                assertFalse(policy.canAccess(plan, active, true));
            }
        }

        @Nested
        @DisplayName("Và gói là PREMIUM")
        class PremiumPlan {
            @BeforeEach
            void selectPlan() {
                plan = DocumentAccessPolicy.Plan.PREMIUM;
            }

            @Test
            @DisplayName("Được đọc tài liệu miễn phí")
            void allowsFreeDocument() {
                assertTrue(policy.canAccess(plan, active, false));
            }

            @Test
            @DisplayName("Được đọc tài liệu premium")
            void allowsPremiumDocument() {
                assertTrue(policy.canAccess(plan, active, true));
            }
        }
    }

    @Nested
    @DisplayName("Khi tài khoản không hoạt động")
    class InactiveAccount {
        @BeforeEach
        void disableAccount() {
            active = false;
        }

        @Test
        @DisplayName("Không được đọc tài liệu miễn phí")
        void deniesFreeDocument() {
            assertFalse(policy.canAccess(
                    DocumentAccessPolicy.Plan.BASIC, active, false));
        }

        @Test
        @DisplayName("Không được đọc tài liệu premium")
        void deniesPremiumDocument() {
            assertFalse(policy.canAccess(
                    DocumentAccessPolicy.Plan.PREMIUM, active, true));
        }
    }

    @Test
    @DisplayName("Từ chối gói null")
    void rejectsNullPlan() {
        assertThrows(NullPointerException.class,
                () -> policy.canAccess(null, true, false));
    }
}
```

Đây là **hai file Java hoàn chỉnh**, có đủ package, class và import để biên dịch trong dự án đã có JUnit Jupiter API/engine. Không cần `@SpringBootTest`: logic này thuần Java, không có bean hay I/O.

Kết quả dự kiến có **7 phương thức `@Test`**, đều pass. Vì mỗi nhóm nằm trong một inner class khác nhau, việc hai nhóm đều có phương thức `allowsFreeDocument()` là hợp lệ; chúng là hai phương thức của hai Java class khác nhau.

Từ IDE, người đọc thường thấy cây gần như sau (cách hiển thị tùy runner):

```text
DocumentAccessPolicyTest
├── Khi tài khoản hoạt động
│   ├── Và gói là BASIC
│   │   ├── Được đọc tài liệu miễn phí             PASS
│   │   └── Bị từ chối tài liệu premium           PASS
│   └── Và gói là PREMIUM
│       ├── Được đọc tài liệu miễn phí             PASS
│       └── Được đọc tài liệu premium             PASS
├── Khi tài khoản không hoạt động
│   ├── Không được đọc tài liệu miễn phí           PASS
│   └── Không được đọc tài liệu premium           PASS
└── Từ chối gói null                              PASS
```

Khi dùng Maven Wrapper trong module chứa cấu hình JUnit 5/Jupiter:

```bash
./mvnw -Dtest=DocumentAccessPolicyTest test
```

Hoặc Gradle Wrapper với JUnit Platform đã bật cho task test:

```bash
./gradlew test --tests "com.example.library.DocumentAccessPolicyTest"
```

Trên Windows, dùng `mvnw.cmd` hoặc `gradlew.bat`; chạy tại đúng thư mục module. Với Spring Boot, dependency `spring-boot-starter-test` thường cung cấp JUnit Jupiter cần thiết. Nếu là project Gradle Java tự cấu hình, bảo đảm có engine và `useJUnitPlatform()`. Kỳ vọng suite có **7 test thành công, 0 thất bại**; không có stdout nghiệp vụ được định nghĩa. Tên/report tree khác nhau giữa IntelliJ, Eclipse, Surefire và Gradle, nhưng các assertion phải giống nhau.

## 3. Lifecycle: setup ở cấp ngoài được thực thi trước cấp trong

Một tính năng quan trọng hơn việc nhóm tên là **kế thừa lifecycle callbacks trên chuỗi chứa lớp inner**. Khi chạy `ActiveAccount.BasicPlan.allowsFreeDocument()`, thứ tự là:

```text
Tạo instance của test (lifecycle mặc định)
  → @BeforeEach của DocumentAccessPolicyTest: createNewPolicy()
  → @BeforeEach của ActiveAccount: enableAccount()
  → @BeforeEach của BasicPlan: selectPlan()
  → @Test: allowsFreeDocument()
  → @AfterEach của BasicPlan (nếu có)
  → @AfterEach của ActiveAccount (nếu có)
  → @AfterEach của DocumentAccessPolicyTest (nếu có)
```

Do đó `policy` được tạo trước khi `ActiveAccount` và `BasicPlan` truy cập, rồi `active` và `plan` được gán đúng bối cảnh. Khi chạy test trong `PremiumPlan`, JUnit không chạy setup của `BasicPlan`. Khi chạy `rejectsNullPlan()` tại lớp ngoài, setup của các nested class không được gọi.

`@BeforeEach` ở lớp ngoài và lớp trong chạy **cho mỗi invocation thuộc nhóm con**, không phải một lần khi nhóm bắt đầu. `@AfterEach` theo chiều ngược lại: cấp trong trước, cấp ngoài sau. Nếu một cấp có nhiều phương thức `@BeforeEach` thì đừng giả định JUnit thực thi theo thứ tự các dòng code; gộp các bước có phụ thuộc thứ tự vào một phương thức rõ ràng.

### Mỗi test có thực sự độc lập?

Với lifecycle mặc định **`TestInstance.Lifecycle.PER_METHOD`**, JUnit tạo đối tượng test tương ứng mới cho từng test method, kể cả các đối tượng ở chuỗi nested. Vì thế các trường thường của lớp test không tự duy trì giá trị qua các phép test khác nhau. Tuy nhiên, **biến static, singleton bean, cơ sở dữ liệu, file và cache ngoài JVM** vẫn có thể được chia sẻ. `@Nested` không tự xóa những tài nguyên này.

Không để kết quả test “đọc tài liệu premium” phụ thuộc việc trước đó test “đăng ký gói premium” đã chạy. Mỗi test cần dựng tình huống riêng và assert kết quả của riêng nó.

## 4. `@BeforeAll`, `@AfterAll` và lifecycle `PER_CLASS`

`@BeforeAll`/`@AfterAll` xử lý thao tác một lần cho nhóm test, ví dụ chuẩn bị fixture dùng chung không thay đổi. Theo `PER_METHOD`, các callback này thông thường phải là `static`; từ Java 16, Java cho phép khai báo static member trong inner class. Khi muốn dùng callback **không static** ở cấp nested, áp dụng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` cho nhóm:

```java
@Nested
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class WithSharedFixture {
    @BeforeAll
    void prepareOnce() {
        // Chỉ thực hiện một lần cho nhóm này.
    }

    @Test
    void checksBehavior() {
        // Thêm assertion thực khi đưa vào dự án.
    }
}
```

Đoạn trên **chỉ minh họa cơ chế lifecycle** trong một lớp test đang có cấu hình JUnit và import phù hợp; nó không phải chương trình độc lập. Khi dùng thực tế, import `org.junit.jupiter.api.TestInstance`, `BeforeAll`, `Nested`, `Test` và viết assertion. Việc chuyển sang `PER_CLASS` đồng nghĩa các test trong nhóm có thể dùng chung instance, nên dễ làm rò rỉ state. Đối với hầu hết unit test, giữ `PER_METHOD` và `@BeforeEach` sẽ ít gây phụ thuộc ngầm hơn.

Dù cần khởi tạo chung, hãy phân biệt dữ liệu **immutable có thể chia sẻ** với trạng thái **mutable cần làm mới**. Chạy song song càng làm nguy cơ tranh chấp và nondeterminism rõ hơn.

## 5. `@Nested` kết hợp `@ParameterizedTest`

`@Nested` nhóm **ngữ cảnh**; `@ParameterizedTest` lặp **cùng một rule với các bộ dữ liệu khác nhau**. Ví dụ, mọi loại gói đều phải bị từ chối khi tài khoản không hoạt động:

```java
@Nested
class InactiveAccount {
    @ParameterizedTest
    @EnumSource(DocumentAccessPolicy.Plan.class)
    void deniesPremiumDocumentsForAllPlans(
            DocumentAccessPolicy.Plan plan) {
        assertFalse(policy.canAccess(plan, false, true));
    }
}
```

Đây là đoạn **bổ sung vào lớp test ngoài có trường `policy`**, không phải file độc lập. Cần import `org.junit.jupiter.params.ParameterizedTest`, `org.junit.jupiter.params.provider.EnumSource`, `org.junit.jupiter.api.Nested`, và static import `assertFalse`; dự án phải có `junit-jupiter-params` phù hợp. Vì `Plan` có hai giá trị, đoạn này tạo **2 lượt thực thi**.

Nếu các giá trị chỉ khác nhau ở input nhưng có chung expected behavior, dùng parameterized test thường gọn hơn nhiều lớp `@Nested`. Nếu từng nhóm có setup và expected behavior khác, `@Nested` thể hiện phạm vi tốt hơn. Có thể dùng cả hai cùng lúc.

## 6. Áp dụng với Spring Boot TestContext

Trong Spring Boot, `@Nested` hữu ích để nhóm kịch bản của `@WebMvcTest`, `@DataJpaTest` hoặc `@SpringBootTest`, nhưng **cấu trúc nested không tự tạo ApplicationContext**.

### Kế thừa cấu hình từ lớp ngoài

Spring TestContext Framework mặc định dùng chế độ **`INHERIT`** khi xử lý nhiều annotation cấu hình test cho nested class. Ví dụ, một lớp ngoài khai báo `@SpringBootTest` và `@ActiveProfiles("test")` có thể để các nhóm con kế thừa cấu hình này:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceIntegrationTest {
    @Autowired
    OrderService service;

    @Nested
    class WhenOrderIsPending {
        @Test
        void canCancel() {
            // Arrange order, gọi service, assert kết quả.
        }
    }

    @Nested
    class WhenOrderIsShipped {
        @Test
        void cannotCancel() {
            // Arrange order đã giao, assert không được hủy.
        }
    }
}
```

Đây là **mã minh họa cách tổ chức Spring test**, chưa biên dịch độc lập vì `OrderService`, import Spring và assertion phụ thuộc ứng dụng cụ thể. Không nên sao chép như một test hoàn chỉnh. Tùy cấu hình test và SpringExtension, bean được inject ở lớp ngoài có thể được các lớp con truy cập.

Spring cung cấp `@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)` khi cần đổi cách kế thừa cấu hình ở nhóm con. Chế độ mặc định cũng có thể bị chỉnh bằng thuộc tính `spring.test.enclosing.configuration`; nếu test con không có annotation/config như dự đoán, hãy kiểm tra cả annotation và cấu hình hệ thống.

### Ba giới hạn cần ghi nhớ

1. **ApplicationContext có thể được cache và dùng lại** giữa các test có cấu hình tương đương. `@Nested` không bảo đảm một context mới cho mỗi lớp con; việc tạo nhiều profile/property khác nhau còn có thể làm tăng số context và thời gian chạy.
2. **Vòng đời test object không đồng nghĩa dữ liệu DB được rollback.** Khi test repository hoặc service, phải có giao dịch/dọn dẹp phù hợp. `@Transactional` trên test có ngữ nghĩa quản lý transaction của Spring Test; thao tác chạy ở tiến trình hoặc thread khác có thể không tham gia transaction đó.
3. **Đừng gắn `@SpringBootTest` chỉ để dùng `@Nested`.** Nếu chỉ kiểm rule thuần Java, JUnit Jupiter là đủ. Khi kiểm HTTP, dùng web slice hoặc integration có scope đúng; khi kiểm DB, cần repository/DB thật hoặc môi trường tương đương.

Ví dụ phân nhóm hữu ích cho controller: `ValidRequests`, `MissingFields`, `Unauthenticated`, `Forbidden`, với assert HTTP status, body và error mapping cụ thể. Nhóm chỉ giúp đọc test; phạm vi bằng chứng vẫn phụ thuộc Spring context, mock và dependency thật mà bài test sử dụng.

## 7. Nguyên tắc tổ chức package và tên test

Đặt test gần mã production cùng trách nhiệm:

```text
src/main/java/com/example/library/DocumentAccessPolicy.java
src/test/java/com/example/library/DocumentAccessPolicyTest.java
```

Giữ **một top-level test class cho một trách nhiệm tương đối rõ**, rồi dùng các inner class `@Nested` cho điều kiện đầu vào/trạng thái. Cách này giúp tìm test từ mã nguồn và tìm các nhánh còn thiếu từ cây kết quả.

Quy ước đặt tên:

- Lớp ngoài: `DocumentAccessPolicyTest` hoặc `OrderControllerTest`.
- Lớp nhóm: `ActiveAccount`, `BasicPlan`, `InvalidRequest`; `@DisplayName` có thể diễn giải thành “Khi...”.
- Test method: tên hành vi ở ngôn ngữ hành động, như `deniesPremiumDocument`, `rejectsNullPlan`.
- Fixture chung: `@BeforeEach` cấp ngoài; fixture chỉ dành riêng nhóm: `@BeforeEach` cấp tương ứng.
- Thường 1–2 cấp nested là dễ theo dõi; đừng tạo các lớp lồng nhau quá sâu khiến một test phải đọc qua nhiều setup.

Không dùng nested test class `static`. Java `static class` lồng nhau là nested class theo cú pháp Java, nhưng JUnit Jupiter **`@Nested` yêu cầu non-static inner class**. Nếu nhóm chỉ để tạo tập dữ liệu tham số cho một rule, dùng `@ParameterizedTest` thay thế.

## 8. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Các phương thức trong lớp con không chạy | Thiếu `@Nested`, lớp khai báo `static`, chạy bằng JUnit 4 runner hoặc thiếu Jupiter engine | Dùng non-static `@Nested class`, cấu hình JUnit Jupiter/Platform |
| `policy` hoặc fixture là `null` | Tưởng setup ở một nhóm anh em cũng chạy cho nhóm khác | Đưa setup chung lên lớp ngoài; setup riêng ở đúng nhóm tổ tiên |
| Test pass khi chạy riêng, fail khi chạy cả nhóm | Static/shared state, DB/file không cleanup, lifecycle `PER_CLASS` chia sẻ state | Chuẩn bị dữ liệu riêng và khôi phục/dọn dẹp sau từng test |
| `@BeforeAll` báo lỗi | Cách khai báo static/lifecycle không phù hợp Java/JUnit | Dùng static callback khi hỗ trợ hoặc `PER_CLASS` với non-static callback |
| Một nhóm làm khởi động quá nhiều Spring context | Cấu hình context/profile khác nhau quá mức | Giảm phạm vi test, dùng slice, quản lý profile và context cache |
| Kết quả báo cáo đẹp nhưng test không phát hiện lỗi | `@DisplayName` rõ nhưng assertion yếu hoặc chỉ kiểm tra non-null | Assert đúng outcome, status, state và trường hợp biên |
| Test dường như chạy khác thứ tự lúc trước | Tưởng các nhóm hoặc method được chạy theo thứ tự khai báo | Thiết kế test độc lập; đừng dựa vào thứ tự giao diện hiển thị |
| Cây test rất sâu | Lồng theo mọi biến thể dữ liệu và mọi điều kiện đơn lẻ | Tối giản tầng; dùng tham số hóa cho nhiều input chung một rule |

**Không dùng `@TestMethodOrder` chỉ để chữa phụ thuộc trạng thái.** Thứ tự test nên được xem là chi tiết vận hành, không phải điều kiện để logic nghiệp vụ pass. Đừng giả định `@Nested` tự chạy serial nếu môi trường bật parallel execution: phải quản lý tài nguyên chia sẻ đúng cách.

## 9. Checklist thực hành

- [ ] Tôi có ít nhất hai bối cảnh thực sự khác nhau cần đặt tên rõ ràng.
- [ ] Mỗi lớp nhóm `@Nested` là inner class **không static**.
- [ ] Các `@Test` có assertion cho hành vi cụ thể, không chỉ tên nhóm đẹp.
- [ ] Setup chung ở cấp ngoài, setup riêng ở cấp trong, đúng thứ tự lifecycle.
- [ ] Test không phụ thuộc thứ tự thực thi hoặc trạng thái mutable từ test khác.
- [ ] `@BeforeAll`/`@AfterAll` và `@TestInstance` được chọn theo vòng đời thật, không dùng để chia sẻ state tùy tiện.
- [ ] Sử dụng `@ParameterizedTest` khi chỉ cần chạy nhiều input cùng expected behavior.
- [ ] Unit test không nạp Spring context nếu không cần; integration test biết rõ config/bean/DB nó dùng.
- [ ] Nếu có Spring TestContext, tôi hiểu quy tắc kế thừa cấu hình nested và cache context.
- [ ] Maven/Gradle phát hiện đầy đủ mọi nhóm test; tôi đã chạy cả lớp và kiểm tra số invocation thực tế.

**Ghi nhớ:** `@Nested` làm rõ **Given (bối cảnh)**, trong khi mỗi `@Test` chứng minh **When/Then (hành vi và kết quả)**. Hãy dùng cấu trúc để thể hiện nghiệp vụ và tránh trạng thái ngầm; thêm tầng lồng nhau chỉ khi tầng đó giúp đọc và duy trì test dễ hơn.

### Tài liệu đọc thêm

- [JUnit User Guide — Nested Tests](https://docs.junit.org/6.0.0/writing-tests/nested-tests.html)
- [JUnit User Guide — Annotations](https://docs.junit.org/6.0.0/writing-tests/annotations)
- [Spring Framework — Nested TestContext Configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)
