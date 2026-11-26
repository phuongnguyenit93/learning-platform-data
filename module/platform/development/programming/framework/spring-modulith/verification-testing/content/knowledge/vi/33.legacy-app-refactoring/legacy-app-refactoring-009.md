# Thiết lập baseline và xử lý vi phạm từng phần

> **Bối cảnh:** Một ứng dụng Spring Boot đã tồn tại nhiều năm có các package nghiệp vụ đan xen, phụ thuộc vòng và truy cập trực tiếp lớp nội bộ. Đội ngũ muốn áp dụng Spring Modulith nhưng không thể sửa toàn bộ kiến trúc trong một pull request. Mục tiêu của bài là tạo **baseline nợ kiến trúc có kiểm soát**, bắt CI từ chối vi phạm mới, rồi giảm dần baseline đến khi có thể dùng kiểm chứng nghiêm ngặt.

## 1. Xác định phạm vi và tiêu chí thành công

Spring Modulith cung cấp mô hình module từ cấu trúc package và các quy tắc kiến trúc: không có chu trình phụ thuộc giữa các application module, module khác chỉ đi qua API được công khai, và tuân thủ danh sách phụ thuộc được cho phép nếu có khai báo. Đối với legacy app, gọi kiểm chứng nghiêm ngặt ngay thường tạo nhiều lỗi khó xử lý đồng thời. Một baseline đóng vai trò **danh sách ngoại lệ tạm thời đã được phê duyệt**, không phải xác nhận thiết kế cũ là đúng.

Một tiến trình triển khai tốt cần đáp ứng đồng thời:

1. Cùng một phạm vi phân tích trên máy lập trình viên và CI.
2. Kết quả baseline lưu trong Git, có người phụ trách và ngày xem xét lại.
3. Một thay đổi chỉ được merge khi **không xuất hiện vi phạm mới hoặc vi phạm cũ tăng thêm**.
4. Khi sửa được vi phạm, baseline phải giảm tương ứng; không giữ ngoại lệ đã hết hiệu lực.
5. Có bằng chứng trước/sau trong pull request và có mốc chuyển sang kiểm chứng nghiêm ngặt.

Phân biệt ba tín hiệu: **số vi phạm hiện tại**, **vi phạm mới so với baseline**, **vi phạm đã loại bỏ**. Chỉ dùng số lượng tổng có thể bỏ sót trường hợp xóa một lỗi cũ nhưng tạo một lỗi mới.

## 2. Cố định mô hình module trước khi đo baseline

Giả sử hệ thống có cấu trúc Java như sau:

~~~text
src/main/java/com/acme/shop/
  ShopApplication.java
  order/
    OrderManagement.java
    internal/OrderRepositoryAdapter.java
  inventory/
    InventoryManagement.java
    internal/StockEntity.java
  billing/
    BillingManagement.java
    internal/InvoiceJpaRepository.java
~~~

Các package ngay dưới gốc ứng dụng như order, inventory, billing được nhận diện mặc định là application module. Package gốc của lớp ứng dụng rất quan trọng: nếu đặt lớp kiểm chứng ở dưới một package nghiệp vụ hoặc trỏ sai lớp ứng dụng, mô hình có thể thiếu module và cho kết quả sai lệch.

Thêm test khám phá cấu trúc (JUnit Jupiter), trước khi đặt quality gate:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureDiscoveryTest {

    @Test
    void inspectExistingModules() {
        var modules = ApplicationModules.of(ShopApplication.class);
        modules.forEach(System.out::println);
        modules.detectViolations().getMessages().forEach(System.out::println);
    }
}
~~~

Test trên **chỉ ghi nhận**, chưa khẳng định kiến trúc hợp lệ. Đội ngũ đọc output để chốt ranh giới, xác nhận tên module và lập danh sách lỗi ban đầu. Không đổi cách phát hiện module hoặc loại trừ package chỉ để làm đẹp số liệu. Nếu cần loại trừ mã generated/framework thực sự ngoài phạm vi nghiệp vụ, ghi rõ lý do và áp dụng nhất quán cho các lần chạy tiếp theo.

Với dự án Gradle, nhóm dependency kiểm thử thường cần ít nhất JUnit Jupiter và Spring Modulith core trên test classpath; có thể dùng starter test nếu dự án đã quản lý phiên bản Modulith:

~~~kotlin
dependencies {
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Version cần được quản lý thống nhất bằng Spring Modulith BOM/plugin quản lý dependency của dự án; không chép một version ngẫu nhiên vào ví dụ. Quá trình kiểm chứng cấu trúc bằng ApplicationModules không cần boot toàn bộ ApplicationContext, database hoặc Docker.

## 3. Phân loại vi phạm theo đường đi phụ thuộc

Đừng bắt đầu bằng việc đổi đồng loạt visibility. Trước hết, xem **module nguồn → kiểu đích → lý do bị cấm** để tìm đúng biên cần sửa:

| Phân loại | Ví dụ trong hệ thống | Cách xử lý ưu tiên | Bằng chứng sau sửa |
|---|---|---|---|
| Truy cập nội bộ module | order sử dụng inventory.internal.StockEntity | Dùng API của inventory, truyền DTO/ID thay vì entity | Không còn lỗi truy cập internal |
| Phụ thuộc vòng | order → billing → inventory → order | Đảo chiều qua port, tách hợp đồng hoặc dùng domain event thích hợp | Đồ thị không còn chu trình |
| Phụ thuộc ngoài danh sách cho phép | billing gọi API order dù allowedDependencies chỉ cho inventory | Cân nhắc nghiệp vụ, sửa chiều gọi hoặc khai báo phụ thuộc hợp lệ có chủ đích | Vi phạm allowedDependencies biến mất |
| Vi phạm DDD bổ sung | Rule của jMolecules báo dependency giữa layer | Phân biệt rule bổ sung với core rule | Log chỉ rõ bộ rule và cấu hình classpath |

**Ví dụ cụ thể:** OrderService đang inject thẳng StockRepositoryAdapter của inventory.internal. Chuyển sang InventoryManagement (API gốc module inventory), với phương thức reserve(productId, quantity). OrderService chỉ biết hợp đồng nghiệp vụ, không biết adapter JPA. Nếu hai module cùng cần một kiểu dữ liệu, ưu tiên hợp đồng nhỏ gọn ở biên; việc chuyển StockEntity sang một package dùng chung thường chỉ che giấu sự phụ thuộc vào chi tiết lưu trữ.

Phân loại còn giúp tạo đơn vị công việc nhỏ: một nhóm dependency, một owner, một pull request; không gộp việc sửa event, database, build, đổi framework cùng lúc nếu không có lý do.

## 4. Chọn cách đóng băng baseline có thể review

Có hai mức bảo vệ:

- **Strict gate:** Gọi ApplicationModules.of(ShopApplication.class).verify(), test chỉ qua khi hoàn toàn không có vi phạm.
- **Legacy gate:** Thu thập kết quả detectViolations(), đối chiếu với baseline đã duyệt, cho phép **đúng những ngoại lệ cũ** và chặn mọi ngoại lệ chưa duyệt.

Không dùng filter với điều kiện quá rộng như message.contains("inventory") hoặc bỏ qua toàn bộ module order: một lỗi mới liên quan inventory sẽ bị che. Nếu có ngoại lệ tạm, định danh đủ cụ thể và có lịch loại bỏ.

Một baseline thực tế có thể gồm:

~~~text
src/test/resources/architecture/modulith-known-violations.sha256
docs/architecture-debt.md  (ví dụ về sổ đăng ký nợ; không bắt buộc)
~~~

File SHA-256 lưu **mỗi dòng một fingerprint của nguyên văn thông điệp vi phạm**, cho phép thông điệp nhiều dòng mà không cần chế ra định dạng escape riêng. Mỗi fingerprint tương ứng với một mô tả vi phạm từ getMessages(). Tài liệu nợ (hoặc issue tracker) ánh xạ fingerprint sang module nguồn/đích, người xử lý, issue và hạn khắc phục.

Hạn chế có chủ đích: hash của thông điệp có thể đổi nếu nâng Spring Modulith/ArchUnit hoặc tên class/line trong thông điệp thay đổi. Khi đó CI sẽ yêu cầu review baseline, đây là điểm kiểm soát thay đổi; hash không phải ID ổn định theo ngữ nghĩa. Nếu thư viện phát ra hai thông điệp **giống nhau tuyệt đối**, bản baseline theo tập hợp sẽ không phân biệt số lần xuất hiện: dự án có yêu cầu đếm trùng phải lưu thêm multiplicity theo hash.

## 5. Cài đặt JUnit gate chống vi phạm mới

Mẫu dưới đây dành cho Java 17+, JUnit Jupiter và Spring Modulith phiên bản có detectViolations(). Giả sử ShopApplication là lớp @SpringBootApplication ở com.acme.shop; file baseline đã tồn tại dưới src/test/resources/architecture/ (có thể ban đầu rỗng). Test **không tự cập nhật baseline**, vì CI không được duyệt nợ kiến trúc thay cho reviewer.

~~~java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureBaselineTest {

    private static final String BASELINE =
            "/architecture/modulith-known-violations.sha256";

    private Map<String, String> actualViolations() {
        return ApplicationModules.of(ShopApplication.class)
                .detectViolations()
                .getMessages()
                .stream()
                .collect(Collectors.toMap(
                        ArchitectureBaselineTest::fingerprint,
                        Function.identity(),
                        (first, ignoredDuplicate) -> first,
                        TreeMap::new));
    }

    private Set<String> approvedFingerprints() throws IOException {
        var resource = getClass().getResourceAsStream(BASELINE);
        if (resource == null) {
            throw new IllegalStateException("Missing baseline resource: " + BASELINE);
        }

        try (var reader = new BufferedReader(
                new InputStreamReader(resource, StandardCharsets.UTF_8))) {
            return reader.lines()
                    .map(String::trim)
                    .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                    .collect(Collectors.toCollection(TreeSet::new));
        }
    }

    @Test
    void mustNotIntroduceOrHideArchitecturalDebt() throws IOException {
        var actual = actualViolations();
        var approved = approvedFingerprints();

        var introduced = new TreeSet<>(actual.keySet());
        introduced.removeAll(approved);
        assertTrue(introduced.isEmpty(), () ->
                "New Modulith violations:\n" + introduced.stream()
                        .map(hash -> hash + "\n" + actual.get(hash))
                        .collect(Collectors.joining("\n\n")));

        var removed = new TreeSet<>(approved);
        removed.removeAll(actual.keySet());
        assertTrue(removed.isEmpty(), () ->
                "Remove resolved/obsolete fingerprints from baseline: " + removed);
    }

    @Test
    @Disabled("Chỉ bật thủ công khi chụp baseline lần đầu; không chạy trong CI")
    void printCandidateBaselineForReview() {
        actualViolations().forEach((hash, message) ->
                System.out.println(hash + "\n" + message + "\n"));
    }

    private static String fingerprint(String message) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(message.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }
}
~~~

**Cách chụp lần đầu:** Bật tạm printCandidateBaselineForReview() ở môi trường local, chạy riêng test đó, review từng lỗi thô kèm hash rồi chép **chỉ những hash được phê duyệt** vào file baseline, một hash một dòng. Sau đó trả test về trạng thái Disabled và chạy mustNotIntroduceOrHideArchitecturalDebt(). Chụp snapshot dựa trên mã đang chạy ở nhánh được thống nhất, không lấy từ output của một nhánh có thay đổi chưa được review.

Hai điều kiện kiểm thử tách biệt: một hash xuất hiện mới thì fail; một hash biến mất nhưng còn trong baseline cũng fail để bắt buộc xóa ngoại lệ cũ. Khi baseline hết mục, kiểm thử không cho phép xuất hiện bất kỳ lỗi mới nào. Ở thời điểm đó có thể thay gate này bằng verify() nghiêm ngặt. Đầu vào được đọc qua classpath resource để tránh phụ thuộc working directory khi Gradle/Maven chạy khác nhau.

## 6. Sửa từng nhóm và thu nhỏ baseline theo pull request

Ví dụ ban đầu có ba nợ kiến trúc được duyệt:

~~~text
DEBT-101: order -> inventory.internal.StockEntity
DEBT-102: inventory -> billing -> order -> inventory (cycle)
DEBT-103: billing -> order (ngoài allowedDependencies)
~~~

Một lộ trình có thứ tự:

1. **PR A:** Thay StockEntity trong order bằng InventoryManagement.reserve(...). Chạy unit/integration test của order; chạy baseline gate; hash của DEBT-101 biến mất nên xóa nó khỏi file baseline cùng trong PR.
2. **PR B:** Đảo chiều lời gọi gây chu trình thông qua interface/port đặt ở phía cần dịch vụ. Chạy lại graph, kiểm thử nghiệp vụ liên quan và bỏ DEBT-102 khi không còn violation.
3. **PR C:** Đánh giá quan hệ billing ↔ order. Nếu được chấp thuận, khai báo allowedDependencies phù hợp; nếu không, chuyển lời gọi sang API đúng owner. Chỉ xóa DEBT-103 sau khi xác nhận lại không còn lỗi.

Số lượng lỗi có thể tăng tạm thời trong **nhánh làm việc** khi refactor từng bước. Pull request cuối cùng vẫn phải qua gate; tránh merge một bước làm baseline phình to rồi hứa sửa sau. Nếu phải tách rollout vì lý do vận hành, chỉ thêm ngoại lệ mới bằng quy trình review và deadline riêng, không tự động cập nhật file bằng kết quả CI.

Đồ thị dự kiến sau refactor:

~~~mermaid
flowchart LR
    Order["order (consumer)"] --> InventoryAPI["inventory: InventoryManagement"]
    Billing["billing (consumer)"] --> OrderAPI["order: OrderManagement"]
    InventoryAPI --> InventoryInternal["inventory.internal"]
    OrderAPI --> OrderInternal["order.internal"]
~~~

Các cạnh vào package internal chỉ được xuất phát từ chính module sở hữu nó; đoạn sơ đồ ở đây minh họa phân tầng biên, không thể thay thế bằng chứng từ detectViolations().

## 7. Chọn giải pháp cho từng kiểu vi phạm, tránh sửa giả

Với trường hợp billing cần gọi chức năng của order, có thể công khai một API trong package gốc order và siết luật bằng package-info.java:

~~~java
// src/main/java/com/acme/shop/billing/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {"order"}
)
package com.acme.shop.billing;
~~~

Khai báo trên chỉ đúng khi phụ thuộc billing → order **được chấp thuận về thiết kế**; nó không cho billing truy cập order.internal. Nếu cần một hợp đồng ở subpackage của order, mô tả hợp đồng đó bằng @NamedInterface trên package-info.java của subpackage và tham chiếu bằng cú pháp order::tên-giao-diện, thay vì mở toàn bộ package nội bộ.

| Cách sửa | Khi nên chọn | Điều cần kiểm chứng |
|---|---|---|
| Chuyển dependency sang API module gốc | Caller chỉ cần hành vi nghiệp vụ | Không còn import class internal; hành vi không đổi |
| Named interface giới hạn | Có SPI/hợp đồng cần xuất ở subpackage | Chỉ API dự định được truy cập |
| Port/interface đảo chiều | Gặp chu trình do adapter hạ tầng gọi ngược nghiệp vụ | Đồ thị module thành DAG; đúng hướng gọi |
| Event nghiệp vụ | Quy trình có thể chấp nhận loose coupling và xử lý async/transactional phù hợp | Test sự kiện, idempotency, transaction và eventual consistency |
| Điều chỉnh allowedDependencies | Quan hệ trực tiếp thật sự hợp lệ | Danh sách thể hiện quyết định thiết kế, không dàn trải tất cả module |

Các cách sửa **không đủ**: chuyển lớp internal sang package gốc mà không thiết kế API; đánh dấu toàn bộ module là open lâu dài; thêm mọi module vào allowedDependencies; hoặc loại trừ package nghiệp vụ khỏi ApplicationModules. Những thao tác đó khiến kết quả xanh nhưng ranh giới thật không được cải thiện.

## 8. Bảo vệ quy trình trong CI và theo dõi tiến độ

Khi local gate đã chạy ổn, chạy cùng test ở CI trước merge. Ví dụ dùng Gradle (tên test tùy dự án):

~~~bash
./gradlew test --tests 'com.acme.shop.ArchitectureBaselineTest'
~~~

Trong pipeline Windows, dùng gradlew.bat thay cho ./gradlew. Lệnh này là minh họa áp dụng trong **repo ứng dụng**, không phải lệnh chạy trong thư mục giáo trình. Với Maven/JUnit, cấu hình Surefire chọn test tương ứng; vẫn nên chạy toàn bộ test suite ở pipeline chính.

Một pull request sửa boundary nên kèm:

- **Trước:** thông điệp vi phạm, module nguồn/đích, hash baseline liên quan, link issue.
- **Thay đổi:** code owner của API và quan hệ phụ thuộc mới; tác động lên transaction/event nếu có.
- **Sau:** output của gate, hash bị xóa, output của business tests và integration tests có liên quan.
- **Review:** xác nhận không thêm wildcard vào ngoại lệ, không làm mất module do thay phạm vi scan, không đưa logic nghiệp vụ vào shared module vô tội vạ.

Theo dõi tiến độ theo **số hash còn trong baseline qua thời gian**, **tuổi ngoại lệ lâu nhất**, **số module đã sạch**, **số chu trình còn tồn tại**, và **số PR bị chặn do phát sinh lỗi mới**. Con số giảm là tín hiệu, nhưng cần đọc diff để tránh việc một thay đổi làm đổi thông điệp mà chưa sửa được vi phạm.

## 9. Kiểm chứng nhiều tầng sau mỗi lần loại bỏ nợ

Architecture test không chứng minh giao dịch, dữ liệu hay tích hợp đã đúng. Khi thay lời gọi repository nội bộ bằng facade công khai, nên kiểm chứng theo ba tầng với mục đích khác nhau:

| Tầng | Công cụ | Bắt được gì | Không khẳng định được |
|---|---|---|---|
| Cấu trúc | ApplicationModules.detectViolations(), sau đó verify() | Chu trình và truy cập sai biên được mô hình hóa | Hành vi API tại runtime |
| Nghiệp vụ | JUnit/Mockito cho hành vi của facade/port | Kết quả, lỗi biên, mapping DTO | Giao dịch DB thật |
| Tích hợp module | @ApplicationModuleTest, test DB hoặc event khi cần | Bean wiring, transaction, event, repository | Không thay được toàn bộ E2E |

Một ca thực hành sau khi sửa DEBT-101: đặt integration test trong com.acme.shop.order, dùng @ApplicationModuleTest với bootstrap mode phù hợp; khởi tạo dữ liệu hoặc mock dependency bên ngoài module có chủ đích; gọi OrderManagement, khẳng định kết quả giữ chỗ và event đúng. Tách ca kiểm chứng business behavior khỏi bài toán baseline để failure có thể quy được nguyên nhân. Nếu một adapter cần database, dùng test database phù hợp để phát hiện lỗi transaction không hiển thị ở architecture graph.

Nâng cấp Spring Modulith/ArchUnit hoặc bật thêm bộ luật jMolecules có thể làm tập violations thay đổi **do rule engine**, không hẳn do PR chức năng. Cần chốt versions cho đợt refactor; khi đổi version, review lại toàn bộ output, phân loại lỗi thật và thay đổi định dạng thông điệp trước khi chỉnh baseline.

## 10. Bài thực hành và điều kiện kết thúc giai đoạn chuyển tiếp

**Đề bài:** Một monolith có ba module order, inventory và billing. Cấu hình ApplicationModules hiện báo 12 violations: 7 truy cập internal, 3 phụ thuộc sai danh sách và 2 chu trình. Đội chỉ có thể sửa 2–3 violation mỗi sprint. Hãy thiết kế một pull request đầu tiên sao cho không làm mất bảo vệ regression.

**Các bước thực hiện:**

1. Xác nhận ShopApplication nằm ở package gốc; in danh sách module để phát hiện module chưa được nhận diện.
2. Chạy detectViolations() để thu thông điệp thật, phân loại đủ 12 lỗi và gắn owner/issue.
3. Chụp 12 fingerprint được duyệt vào file baseline; chạy gate, kỳ vọng **PASS** trên trạng thái hiện tại.
4. Cố ý thêm import từ billing vào inventory.internal rồi chạy lại; kỳ vọng **FAIL** kèm thông điệp về lỗi mới.
5. Hoàn tác import thử nghiệm; sửa một truy cập internal bằng API công khai; chạy gate, kỳ vọng **FAIL vì hash baseline đã hết hiệu lực**.
6. Xóa fingerprint tương ứng, chạy lại gate và test hành vi; kỳ vọng **PASS**, baseline còn 11 hash nếu mỗi thông điệp là riêng biệt.
7. Review diff để bảo đảm không có package nghiệp vụ nào bị loại khỏi scan.

**Tiêu chí đạt:** Có một test JUnit tái lập được, baseline được commit và theo dõi, canary thêm lỗi mới bị chặn, một vi phạm thật được sửa và hash của nó được gỡ. Nếu một canary mới vẫn PASS, kiểm tra lại phạm vi phát hiện module và cách xây fingerprint trước khi cho merge.

Khi baseline bằng 0 và cấu trúc module đã ổn định, dùng gate nghiêm ngặt:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class StrictArchitectureTest {

    @Test
    void everyApplicationModuleRespectsItsBoundary() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**Tài liệu đối chiếu:** [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html), [Fundamentals – ApplicationModules và package discovery](https://docs.spring.io/spring-modulith/reference/fundamentals.html), [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html), [Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html).
