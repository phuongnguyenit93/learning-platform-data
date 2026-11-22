# Coverage dòng mã khác với kiểm chứng hành vi và rủi ro

## 1. Coverage cho biết test đã đi qua mã nào

Code coverage là số liệu cho biết một phần mã nguồn hoặc bytecode đã được thực thi trong một lần chạy test. Với line coverage, công cụ ghi nhận những dòng mã có ít nhất một instruction tương ứng được chạy. Tỷ lệ thường được biểu diễn như sau:

\[
\text{Line coverage} =
\frac{\text{số dòng được thực thi}}{\text{tổng số dòng có thể đo}} \times 100\%
\]

Ví dụ, nếu trong 100 dòng có thể đo, test đã thực thi ít nhất một instruction ở 85 dòng, line coverage là 85%.

Số liệu này trả lời một câu hỏi hữu ích: **những vùng mã nào chưa được test chạy tới?** Nó không tự trả lời các câu hỏi quan trọng hơn về chất lượng:

- Kết quả có đúng với yêu cầu nghiệp vụ không?
- Test có phát hiện được khi implementation trả kết quả sai không?
- Các nhánh lỗi, dữ liệu biên và trạng thái bất thường đã được kiểm tra chưa?
- Những phần có tác động lớn khi lỗi có được kiểm thử đủ sâu không?
- Test có đang kiểm tra hợp đồng của hệ thống hay chỉ chạy qua code?

Vì thế, coverage là công cụ quan sát phạm vi thực thi. Kiểm chứng hành vi xác nhận kết quả và side effect mà người dùng hoặc hệ thống phụ thuộc. Đánh giá rủi ro giúp quyết định nên đầu tư test sâu vào phần nào.

## 2. Phân biệt line coverage với các loại coverage khác

Các công cụ như JaCoCo đo nhiều loại coverage ở mức bytecode. Những loại phổ biến gồm:

| Chỉ số | Nó đo điều gì? | Câu hỏi nó giúp trả lời |
|---|---|---|
| Instruction coverage | Tỷ lệ instruction bytecode đã chạy | Bao nhiêu instruction được thực thi? |
| Line coverage | Tỷ lệ dòng nguồn có instruction được thực thi | Dòng nguồn nào đã được chạm tới? |
| Branch coverage | Tỷ lệ nhánh điều kiện đã được thực thi | Các hướng true/false hoặc nhánh switch đã được đi qua chưa? |
| Method coverage | Tỷ lệ method đã được gọi | Method nào đã được thực thi? |
| Class coverage | Tỷ lệ class đã được nạp/thực thi theo cách công cụ định nghĩa | Class nào có tham gia lần chạy test? |
| Complexity coverage | Mức độ bao phủ các đường đi độc lập được công cụ suy ra từ độ phức tạp | Những đường đi logic nào còn thiếu? |

Line coverage và branch coverage có liên quan nhưng không thay thế nhau. Một dòng `if` có thể được thực thi khi điều kiện đúng hoặc sai. Nếu test chỉ đi qua một phía, dòng đó vẫn được tính là covered dù nhánh còn lại chưa từng chạy.

Ví dụ:

```java
if (account.isActive()) {
    sendNotification(account);
}
```

Test với tài khoản active thực thi dòng `if` và phần thân. Nó chưa kiểm tra trường hợp tài khoản inactive, dù trường hợp đó có thể quan trọng về quyền riêng tư hoặc chi phí gửi thông báo.

Branch coverage giúp phát hiện thiếu nhánh. Tuy nhiên, kể cả 100% branch coverage cũng không chứng minh mọi tổ hợp đầu vào, trạng thái hệ thống hoặc chuỗi sự kiện đều đã được kiểm tra.

## 3. Một test có thể đạt 100% line coverage nhưng kiểm tra hành vi rất yếu

Xét một bộ tính giá có hai loại giảm giá:

```java
public class PriceCalculator {

    public BigDecimal finalPrice(
            BigDecimal subtotal,
            boolean vip,
            boolean coupon) {
        BigDecimal discount = BigDecimal.ZERO;

        if (vip) {
            discount = discount.add(subtotal.multiply(new BigDecimal("0.10")));
        }

        if (coupon) {
            discount = discount.add(subtotal.multiply(new BigDecimal("0.05")));
        }

        return subtotal.subtract(discount);
    }
}
```

Test sau gọi method với cả hai điều kiện đúng:

```java
@Test
void calculatesPrice() {
    BigDecimal result = calculator.finalPrice(
            new BigDecimal("100.00"), true, true);

    assertThat(result).isNotNull();
}
```

Test này thực thi tất cả các dòng trong method, nên line coverage của method có thể đạt 100%. Nhưng assertion chỉ kiểm tra kết quả không null. Nếu implementation trả `100.00`, `95.00` hoặc một giá trị sai khác, test vẫn pass.

Test cũng chưa chạy các nhánh `vip = false` và `coupon = false`. Do đó branch coverage thấp hơn line coverage. Quan trọng hơn, test chưa xác nhận hợp đồng giảm giá: VIP được giảm 10%, coupon được giảm 5%, hai mức có được cộng hay áp dụng theo thứ tự, và giá có được làm tròn đúng hay không.

Một implementation sai như sau vẫn có thể được thực thi đầy đủ bởi test trên:

```java
return subtotal;
```

Test chỉ dùng `isNotNull()` sẽ không phát hiện lỗi. Đây là ví dụ rõ ràng cho thấy việc chạy qua code không đồng nghĩa với việc xác nhận code hoạt động đúng.

## 4. Kiểm chứng hành vi bằng kết quả quan sát được

Behavior test tập trung vào hợp đồng của thành phần: đầu vào nào được chấp nhận, đầu ra nào được trả về, trạng thái nào được thay đổi và collaborator nào được gọi với dữ liệu gì.

Với `PriceCalculator`, test nên xác nhận kết quả cụ thể:

```java
@Test
void appliesVipAndCouponDiscounts() {
    BigDecimal result = calculator.finalPrice(
            new BigDecimal("100.00"), true, true);

    assertThat(result).isEqualByComparingTo("85.00");
}
```

Assertion này bảo vệ hành vi cộng hai mức giảm giá. Nếu code bị thay bằng `return subtotal`, test sẽ thất bại.

Kiểm tra thêm các trường hợp độc lập:

```java
@ParameterizedTest
@CsvSource({
        "true,  false, 90.00",
        "false, true,  95.00",
        "false, false, 100.00",
        "true,  true,  85.00"
})
void appliesDiscountsForEachCombination(
        boolean vip,
        boolean coupon,
        String expected) {

    BigDecimal result = calculator.finalPrice(
            new BigDecimal("100.00"), vip, coupon);

    assertThat(result).isEqualByComparingTo(expected);
}
```

Test này kiểm tra bốn tổ hợp của hai điều kiện boolean. Nó tăng branch coverage và xác nhận các kết quả nghiệp vụ quan trọng. Nếu nghiệp vụ có thêm điều kiện như coupon hết hạn, giá trị đơn tối thiểu hoặc không cho phép tổng giảm vượt subtotal, cần bổ sung các trường hợp tương ứng.

Không nên viết test chỉ để chạm vào một dòng. Hãy viết test cho quy tắc mà dòng đó biểu diễn. Khi một dòng code không có ý nghĩa nghiệp vụ riêng, không cần tạo test riêng chỉ để làm phần trăm tăng lên.

## 5. Test cần xác nhận cả nhánh thành công và nhánh thất bại

Một chức năng thường có nhiều kết quả quan sát được. Ví dụ một service chuyển tiền có thể:

- Chấp nhận giao dịch khi số dư đủ và tài khoản hợp lệ.
- Từ chối khi số dư không đủ.
- Từ chối khi tài khoản bị khóa.
- Không trừ tiền nếu ghi nhận giao dịch thất bại.
- Phát sự kiện hoặc ghi audit đúng sau khi giao dịch thành công.

Test hành vi cần xác nhận các hợp đồng này, không chỉ thực thi các câu lệnh trong service.

```java
@Test
void doesNotDebitWhenBalanceIsInsufficient() {
    Account account = accountWithBalance("20.00");

    assertThatThrownBy(() -> transferService.transfer(
            account, destinationAccount(), new BigDecimal("50.00")))
            .isInstanceOf(InsufficientFundsException.class);

    assertThat(account.balance()).isEqualByComparingTo("20.00");
    verifyNoInteractions(transferRepository);
}
```

Test trên xác nhận cả exception, trạng thái tài khoản và việc không ghi giao dịch. Chỉ kiểm tra exception có thể bỏ sót lỗi side effect, chẳng hạn tiền đã bị trừ trước khi service ném lỗi.

Đối với nhánh thành công, kiểm tra trạng thái sau cùng và các side effect nằm trong hợp đồng. Nếu một sự kiện chỉ được phát sau commit, test tích hợp cần xác nhận sự kiện được xử lý đúng phase; chỉ verify method được gọi trước commit có thể không chứng minh dữ liệu đã commit.

## 6. Branch coverage vẫn chưa phải path coverage

Một method có nhiều điều kiện độc lập có thể có rất nhiều tổ hợp. Giả sử có bốn điều kiện boolean, số tổ hợp tối đa là:

\[
2^4 = 16
\]

Một bộ test có thể chạy cả true và false cho từng nhánh mà chưa chạy mọi tổ hợp. Branch coverage có thể đạt 100% trong khi một số tương tác giữa điều kiện chưa được kiểm tra.

Ví dụ:

```java
if (customer.isActive()) {
    if (customer.hasVerifiedEmail()) {
        if (order.total().compareTo(minimum) >= 0) {
            approve(order);
        }
    }
}
```

Các điều kiện có thể tương tác: đơn hàng đạt mức tối thiểu nhưng email chưa xác minh; khách hàng active nhưng bị khóa ở một policy khác; hoặc tổng tiền biên đúng bằng ngưỡng. Test nên chọn các tổ hợp có ý nghĩa theo quy tắc nghiệp vụ và rủi ro, không nhất thiết chạy toàn bộ Cartesian product nếu tổ hợp quá lớn.

Các chiến lược hữu ích gồm:

- **Boundary value analysis**: kiểm tra ngay dưới, đúng bằng và ngay trên ngưỡng.
- **Equivalence partitioning**: chia đầu vào thành các nhóm có hành vi tương đương và chọn đại diện.
- **Decision table**: liệt kê các điều kiện và kết quả tương ứng.
- **Pairwise testing**: chọn bộ dữ liệu để mọi cặp giá trị điều kiện quan trọng xuất hiện ít nhất một lần.
- **Property-based testing**: sinh nhiều đầu vào để kiểm tra invariant hoặc quan hệ tổng quát.

Branch coverage cho biết nhánh đã chạy; các kỹ thuật trên giúp chọn tổ hợp đầu vào có ý nghĩa.

## 7. Coverage không cho biết assertion có đủ mạnh hay không

Một test có thể thực thi nhiều code nhưng không kiểm tra kết quả. Một số dấu hiệu test yếu:

- Chỉ gọi method mà không có assertion.
- Chỉ kiểm tra object khác null hoặc collection không rỗng.
- Chỉ kiểm tra status `200` mà không xác nhận body quan trọng.
- Mock tất cả collaborator và chỉ verify một lời gọi không có ý nghĩa nghiệp vụ.
- Bắt exception rồi bỏ qua, khiến test vẫn pass khi lỗi xảy ra ngoài dự kiến.
- Dùng dữ liệu quá đơn giản, không chạm các trường hợp biên.
- Assertion chỉ kiểm tra một field trong response có nhiều field quan trọng.

Ví dụ test API chỉ kiểm tra status:

```java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestJson))
        .andExpect(status().isCreated());
```

Nếu hợp đồng API yêu cầu trả order id, trạng thái và tổng tiền, test nên kiểm tra các field đó:

```java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestJson))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.id").isNotEmpty())
        .andExpect(jsonPath("$.status").value("CREATED"))
        .andExpect(jsonPath("$.total").value(85.00));
```

Assertion cần tập trung vào phần hợp đồng mà client phụ thuộc. Không nhất thiết kiểm tra mọi field nội bộ hoặc chi tiết triển khai; kiểm tra quá mức có thể làm test giòn khi refactor dù hành vi công khai không đổi.

## 8. Dùng mutation testing để đánh giá khả năng phát hiện lỗi

Mutation testing tạo ra các biến thể nhỏ nhưng có chủ đích của implementation, gọi là mutants. Ví dụ công cụ có thể:

- Đổi `>` thành `>=`.
- Thay `true` thành `false`.
- Thay phép cộng bằng phép trừ.
- Bỏ một lời gọi method.
- Thay giá trị trả về bằng giá trị mặc định.

Sau đó chạy lại test. Nếu test thất bại vì phát hiện thay đổi, mutant được xem là killed. Nếu test vẫn pass, mutant sống sót và có thể chỉ ra một khoảng trống trong assertion hoặc dữ liệu kiểm thử.

\[
\text{Mutation score} =
\frac{\text{số mutant bị kill}}{\text{số mutant có thể đánh giá}} \times 100\%
\]

Một số mutant có thể tương đương về hành vi hoặc không thể đánh giá do cấu trúc code; công cụ thường phân loại riêng. Mutation score không phải thước đo hoàn hảo, nhưng nó cung cấp một góc nhìn về việc test có phát hiện thay đổi logic hay không.

Ví dụ với `PriceCalculator`, nếu mutant đổi VIP discount từ `0.10` thành `0.01`, test chỉ dùng `isNotNull()` vẫn pass. Test so sánh chính xác `85.00` sẽ phát hiện mutant.

Mutation testing thường tốn thời gian hơn coverage vì phải chạy test nhiều lần. Có thể áp dụng trước cho module có logic quan trọng, hoặc trên một tập test/changed code phù hợp thay vì bắt buộc toàn bộ repository trong mỗi lần build.

## 9. Đánh giá rủi ro để ưu tiên test

Không phải mọi dòng code có mức độ quan trọng như nhau. Một nhánh định dạng log ít tác động hơn nhánh tính tiền, phân quyền, cập nhật số dư hoặc migration dữ liệu.

Một cách đơn giản để xếp ưu tiên là đánh giá:

- **Impact**: hậu quả nếu code hoạt động sai, ví dụ mất dữ liệu, sai tiền, lộ thông tin, ngừng dịch vụ.
- **Likelihood**: khả năng lỗi xảy ra do độ phức tạp, thay đổi thường xuyên, phụ thuộc bên ngoài hoặc lịch sử lỗi.
- **Exposure**: mức độ thường xuyên hoặc phạm vi người dùng/hệ thống bị ảnh hưởng.

Đội ngũ có thể dùng thang điểm định tính hoặc số nhỏ, chẳng hạn 1–5 cho impact và likelihood. Điểm tích hợp giúp thảo luận và sắp xếp ưu tiên; nó không phải xác suất khoa học hay một chuẩn chung áp dụng cho mọi tổ chức.

Ví dụ ma trận đơn giản:

| Khu vực | Impact nếu lỗi | Khả năng phát sinh lỗi | Ưu tiên test |
|---|---|---|---|
| Tính phí và hoàn tiền | Cao | Trung bình/cao | Rất cao |
| Authorization và tenant isolation | Rất cao | Trung bình | Rất cao |
| Migration và cập nhật dữ liệu | Cao | Trung bình | Cao |
| Retry khi gọi payment provider | Cao | Cao | Rất cao |
| Định dạng thông báo nội bộ | Thấp/trung bình | Thấp | Thấp hơn |
| Tiện ích format chuỗi đơn giản | Thấp | Thấp | Theo mức sử dụng |

Coverage toàn dự án có thể che giấu một vùng rủi ro cao đang thiếu test. Ví dụ 95% line coverage toàn repository không có nhiều ý nghĩa nếu module phân quyền chỉ có 20% coverage và chưa test trường hợp truy cập trái phép.

Hãy đánh giá coverage theo module hoặc package quan trọng và đối chiếu với danh sách rủi ro. Với phần rủi ro cao, cần test hành vi, negative cases, boundary cases, integration với dependency và khả năng phục hồi khi lỗi xảy ra.

## 10. Ma trận hành vi và rủi ro giúp thiết kế test có mục tiêu

Trước khi thêm test, hãy viết ra hành vi công khai và điều gì có thể sai. Ví dụ với API tạo đơn hàng:

| Hành vi | Rủi ro nếu sai | Kiểm chứng cần có |
|---|---|---|
| Tạo đơn hàng với dữ liệu hợp lệ | Đơn không được tạo hoặc tổng tiền sai | Status, response fields và dữ liệu được lưu |
| Thiếu sản phẩm | Tạo đơn không hợp lệ | Validation error và không ghi dữ liệu |
| Giá sản phẩm thay đổi trong lúc checkout | Dùng sai giá hoặc tính tiền không nhất quán | Quy tắc snapshot giá và transaction/concurrency test |
| Người dùng truy cập đơn của tenant khác | Rò rỉ dữ liệu | Authorization test cho cả allow và deny |
| Payment provider timeout | Giao dịch ở trạng thái không rõ ràng hoặc thu tiền lặp | Retry/idempotency và trạng thái cuối |
| Event được phát sau commit | Gửi thông báo cho đơn đã rollback | Transactional event test và xử lý lỗi downstream |

Từ ma trận này, chọn test ở tầng phù hợp:

- Unit test cho quy tắc tính toán và validation thuần.
- Integration test cho repository, transaction và persistence.
- MVC/API test cho status, header, body, validation và security filter.
- Contract test cho tương tác với dịch vụ bên ngoài.
- End-to-end test cho một số luồng quan trọng qua nhiều thành phần.

Không cần mọi hành vi đều được kiểm tra ở mọi tầng. Chọn tầng gần nguyên nhân lỗi nhất để test nhanh, sau đó thêm integration test cho các ranh giới có rủi ro.

## 11. Dùng JaCoCo trong dự án Gradle

JaCoCo là công cụ phổ biến để thu thập coverage cho Java. Plugin Gradle có thể tạo báo cáo HTML/XML và áp dụng ngưỡng coverage trong build.

Ví dụ `build.gradle.kts`:

```kotlin
plugins {
    java
    jacoco
}

tasks.test {
    useJUnitPlatform()
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)

    reports {
        html.required.set(true)
        xml.required.set(true)
        csv.required.set(false)
    }
}

tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            element = "BUNDLE"
            limit {
                counter = "LINE"
                value = "COVEREDRATIO"
                minimum = "0.80".toBigDecimal()
            }
        }
    }
}

tasks.check {
    dependsOn(tasks.jacocoTestCoverageVerification)
}
```

Ví dụ đặt ngưỡng line coverage 80% cho bundle. Đây chỉ là cấu hình minh họa; ngưỡng thực tế nên dựa trên baseline, độ trưởng thành của dự án và mức rủi ro. Không nên sao chép một tỷ lệ tùy ý rồi coi đó là tiêu chuẩn chất lượng.

Các task quan trọng:

- `test`: chạy test và thu thập execution data khi JaCoCo agent được gắn.
- `jacocoTestReport`: tạo báo cáo coverage; ví dụ trên yêu cầu nó chạy sau test.
- `jacocoTestCoverageVerification`: kiểm tra các rule và làm build thất bại nếu vi phạm.
- `check`: task kiểm tra tổng hợp; ví dụ nối coverage verification vào lifecycle này.

Trong Gradle, `jacocoTestReport` không mặc định phụ thuộc vào `test` ở mọi cấu hình. Vì vậy, ví dụ khai báo `dependsOn(tasks.test)`. Coverage verification cũng cần được nối vào task lifecycle mà CI thực sự chạy, ví dụ `check`.

### 11.1. Chọn counter và scope cho rule

JaCoCo hỗ trợ các counter như `INSTRUCTION`, `LINE`, `BRANCH`, `COMPLEXITY`, `METHOD` và `CLASS`. Rule có thể áp dụng ở mức bundle, package, class hoặc source file tùy cấu hình.

Ví dụ kiểm tra branch coverage:

```kotlin
tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            element = "BUNDLE"
            limit {
                counter = "BRANCH"
                value = "COVEREDRATIO"
                minimum = "0.70".toBigDecimal()
            }
        }
    }
}
```

Không nhất thiết đặt cùng một ngưỡng cho mọi package. Module xử lý tiền hoặc authorization có thể cần tiêu chuẩn hành vi và branch test cao hơn tiện ích đơn giản. Nếu áp dụng rule riêng cho package, hãy đảm bảo include/exclude pattern khớp đúng tên package và không vô tình loại vùng quan trọng khỏi báo cáo.

### 11.2. Đọc báo cáo thay vì chỉ nhìn phần trăm tổng

Báo cáo HTML JaCoCo hiển thị coverage theo package, class, method và dòng nguồn. Dòng màu đỏ thường biểu thị chưa được thực thi, màu vàng thể hiện một phần branch chưa chạy, màu xanh biểu thị phần được cover theo metric tương ứng.

Khi mở báo cáo, hãy tìm:

- Package quan trọng có coverage thấp.
- Method có nhiều nhánh nhưng chỉ chạy một hướng.
- Dòng lỗi hoặc validation chưa được test.
- Class mới thêm trong thay đổi gần đây nhưng chưa có test.
- Phần trăm cao nhờ nhiều code đơn giản trong khi logic rủi ro cao chưa được bảo vệ.

Đừng chỉ nhìn con số tổng ở đầu báo cáo. Một báo cáo có giá trị khi nó dẫn tới câu hỏi cụ thể: hành vi nào chưa được xác nhận và rủi ro nào đang bị bỏ ngỏ?

## 12. Ngưỡng coverage trong CI nên được dùng thế nào?

CI có thể dùng coverage gate để ngăn code mới làm giảm đáng kể phạm vi test. Nhưng một ngưỡng toàn dự án có thể bị đánh lừa bởi code cũ hoặc các package có nhiều dòng dễ cover.

Một cách tiếp cận thực tế:

1. Đo baseline coverage hiện tại và lưu báo cáo làm mốc.
2. Đặt ngưỡng vừa sức cho toàn dự án để không làm build cũ thất bại hàng loạt.
3. Với code mới hoặc code thay đổi, yêu cầu test cho các hành vi mới và không làm giảm coverage ở vùng liên quan.
4. Đặt rule riêng cho module có rủi ro cao nếu có lý do rõ ràng.
5. Theo dõi xu hướng coverage và test quality thay vì tối ưu một lần chạy.
6. Review các exclusion và lý do loại trừ định kỳ.

Diff coverage (coverage của phần code thay đổi) có thể giúp review pull request tập trung hơn. Tuy nhiên, công cụ diff coverage cần map đúng source revision và execution data; nếu pipeline không khớp commit, kết quả có thể sai hoặc thiếu. Nó vẫn chỉ đo code được thực thi, không thay thế việc review assertion.

Không nên yêu cầu 100% coverage một cách máy móc. Một số code sinh tự động, adapter mỏng hoặc nhánh phụ thuộc môi trường có thể không đáng để test trực tiếp; ngược lại, một method chỉ có vài dòng vẫn có thể mang rủi ro cao nếu xử lý quyền hoặc giao dịch tiền.

## 13. Cẩn trọng khi loại trừ code khỏi coverage

JaCoCo hỗ trợ cấu hình include/exclude để loại class khỏi report hoặc verification. Một số exclusion có thể hợp lý, ví dụ code sinh tự động, class cấu hình không chứa logic hoặc lớp bootstrap không thể quan sát qua test.

Nhưng exclusion cũng có thể làm số liệu đẹp lên mà không tăng chất lượng. Không loại trừ chỉ vì:

- Class khó test.
- Branch đang làm giảm phần trăm.
- Code có nhiều exception path.
- Test chưa được viết.
- Module có rủi ro cao nhưng khó tạo fixture.

Nếu một vùng khó test, hãy xem xét thiết kế lại dependency để có thể kiểm thử, tạo adapter/interface ở ranh giới I/O, hoặc kiểm tra ở tầng integration phù hợp. Nếu cần exclusion, ghi lý do và phạm vi rõ ràng để reviewer hiểu vì sao phần đó không nằm trong metric.

Coverage report cũng phụ thuộc vào cấu hình source set, test task và class được instrument. Nếu CI chỉ chạy unit test mà bỏ qua integration test, số liệu có thể không phản ánh các test cần thiết. Ngược lại, nếu cùng class được đo từ nhiều task, cần hợp nhất execution data đúng cách để tránh báo cáo thiếu hoặc gây hiểu lầm.

## 14. Kết hợp coverage với các tín hiệu chất lượng khác

Không có một chỉ số đơn lẻ nào mô tả đầy đủ test quality. Nên xem coverage cùng những bằng chứng khác:

| Tín hiệu | Điều nó cho biết | Giới hạn |
|---|---|---|
| Line/branch coverage | Mã nào đã được thực thi | Không xác nhận kết quả đúng |
| Assertion quality | Test kiểm tra hợp đồng và side effect nào | Khó đo tự động bằng một tỷ lệ đơn giản |
| Mutation score | Test có phát hiện một số thay đổi logic có chủ đích không | Mutant có thể tương đương hoặc không đại diện lỗi thực |
| Defect escape/production incident | Lỗi nào đã vượt qua test và đến môi trường thật | Phụ thuộc cách ghi nhận và bối cảnh vận hành |
| Flaky test rate | Test có ổn định qua nhiều lần chạy không | Không đo trực tiếp độ đúng của business logic |
| Test duration | Feedback loop nhanh hay chậm | Test nhanh chưa chắc kiểm tra đủ rủi ro |
| Contract/integration results | Ranh giới giữa các thành phần có hoạt động đúng không | Chỉ bao phủ dependency và môi trường được dựng |

Nếu coverage tăng nhưng số lỗi production không giảm, có thể test đang chạy qua code mà không kiểm tra đúng hành vi. Nếu mutation score thấp, assertion có thể yếu hoặc test data chưa phân biệt được implementation đúng và sai. Nếu test flaky, tín hiệu CI mất độ tin cậy dù coverage cao.

## 15. Thiết kế test theo rủi ro: ví dụ authorization

Giả sử một endpoint chỉ cho phép người dùng cùng tenant xem đơn hàng. Line coverage có thể đạt cao chỉ với test admin hợp lệ. Nhưng rủi ro lớn nhất có thể là user tenant A đọc được đơn hàng tenant B.

Một bộ test hành vi nên gồm:

```java
@Test
void allowsUserToReadOrderInOwnTenant() {
    authenticate(user("alice", "tenant-a"));

    OrderResponse response = orderService.findOrder("order-a-1");

    assertThat(response.id()).isEqualTo("order-a-1");
}

@Test
void deniesUserFromAnotherTenant() {
    authenticate(user("alice", "tenant-a"));

    assertThatThrownBy(() -> orderService.findOrder("order-b-1"))
            .isInstanceOf(AccessDeniedException.class);
}

@Test
void deniesAnonymousUser() {
    clearAuthentication();

    assertThatThrownBy(() -> orderService.findOrder("order-a-1"))
            .isInstanceOf(AuthenticationCredentialsNotFoundException.class);
}
```

Các method `authenticate(...)` và `clearAuthentication()` là helper minh họa, phụ thuộc cách test security context của dự án. Với kiểm thử HTTP, nên gửi request qua security filter chain thực tế và xác nhận status/body phù hợp.

Ba trường hợp này tập trung vào policy: cho phép trong tenant, từ chối cross-tenant và từ chối anonymous. Một test duy nhất với admin có thể chạy qua gần hết dòng code nhưng bỏ sót chính lỗi nghiêm trọng nhất.

## 16. Property-based testing và invariant

Với một số domain, khó liệt kê mọi đầu vào. Property-based testing sinh nhiều dữ liệu và kiểm tra các invariant phải luôn đúng.

Ví dụ với bộ tính giá, có thể kiểm tra những tính chất như:

- Giá cuối không âm nếu domain quy định không có khoản tín dụng âm.
- Không áp dụng coupon thì kết quả không thấp hơn kết quả khi áp dụng coupon hợp lệ.
- Cùng đầu vào phải cho cùng kết quả nếu calculator thuần và deterministic.
- Tổng giảm giá không vượt mức tối đa được business rule cho phép.

Một ví dụ minh họa với jqwik:

```java
@Property
void finalPriceNeverExceedsSubtotal(
        @ForAll @DoubleRange(min = 0.0, max = 100_000.0) double amount) {

    BigDecimal subtotal = BigDecimal.valueOf(amount);
    BigDecimal result = calculator.finalPrice(subtotal, false, false);

    assertThat(result).isEqualByComparingTo(subtotal);
}
```

Property này kiểm tra một invariant trên nhiều giá trị được sinh. Nó không thay thế các test ví dụ cụ thể cho quy tắc VIP/coupon, nhưng giúp tìm lỗi ở các giá trị ít được nghĩ tới.

Property-based test cần giới hạn domain và quy tắc sinh dữ liệu phù hợp. Nếu đầu vào có tiền tệ, scale, rounding hoặc số âm, generator phải phản ánh đúng domain thay vì dùng một kiểu số không phù hợp.

## 17. Khi nào nên xem coverage là tín hiệu cảnh báo?

Coverage thấp có thể chỉ ra code chưa được chạy. Hãy ưu tiên xem xét khi:

- Một nhánh xử lý lỗi chưa được thực thi.
- Một method mới thay đổi business rule chưa có test.
- Module nhạy cảm như thanh toán, authorization, dữ liệu cá nhân hoặc migration có vùng chưa cover.
- Refactor lớn làm coverage giảm bất thường.
- Một class chỉ được test gián tiếp qua mock và chưa có integration test ở ranh giới cần thiết.

Coverage cao cũng cần xem xét nếu:

- Test chỉ gọi method nhưng thiếu assertion có ý nghĩa.
- Nhiều collaborator bị mock khiến test không xác nhận transaction, serialization hoặc filter thực tế.
- Test chỉ đi qua happy path.
- Test không phát hiện mutant đơn giản.
- Code được exclude rộng để đạt ngưỡng.
- Một module rủi ro cao có ít test hơn module tiện ích.

Coverage thấp không tự chứng minh code kém; coverage cao không tự chứng minh code tốt. Cả hai là tín hiệu để hỏi tiếp, dựa trên hành vi và tác động của lỗi.

## 18. Quy trình dùng coverage trong code review và CI

Khi review một thay đổi, có thể đi theo trình tự:

1. Đọc yêu cầu và xác định các hành vi mới hoặc thay đổi.
2. Liệt kê lỗi có hậu quả lớn nếu implementation sai.
3. Xác định các input class, boundary, nhánh thành công và nhánh thất bại.
4. Chọn tầng test phù hợp: unit, slice, integration, contract hoặc end-to-end.
5. Chạy test và xem coverage để tìm code mới chưa được thực thi.
6. Đọc assertion để xác nhận test sẽ thất bại khi hành vi sai.
7. Với logic rủi ro cao, cân nhắc mutation test hoặc property-based test.
8. Kiểm tra CI gate, exclusion và báo cáo theo package/module.
9. Ghi rõ phần chưa kiểm chứng và lý do chấp nhận rủi ro còn lại.

CI nên cung cấp báo cáo dễ truy cập, ngưỡng có chủ đích và kết quả test ổn định. Khi build fail do coverage, thông báo cần chỉ ra package/class/metric vi phạm để developer biết cần bổ sung test ở đâu.

Không nên viết thêm test chỉ để chạy qua dòng đỏ mà không có assertion. Hãy tìm hành vi mà dòng đó đại diện và xác định hậu quả nếu nó sai. Nếu không có hành vi hoặc rủi ro đáng kể, cân nhắc xem code có cần tồn tại hoặc có thể đơn giản hóa hay không.

## 19. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| 100% line coverage nghĩa là code không có bug | Nó chỉ nói các dòng có thể đo đã được thực thi; assertion, input và trạng thái vẫn có thể thiếu |
| 100% branch coverage nghĩa là mọi tình huống đã được test | Tổ hợp điều kiện, chuỗi sự kiện, concurrency và dữ liệu biên vẫn có thể chưa được kiểm tra |
| Coverage càng cao thì test càng tốt | Chỉ số cần được đọc cùng hành vi, assertion, mutation và rủi ro |
| Mọi package phải có cùng một ngưỡng | Mức rủi ro và bản chất code khác nhau |
| Thêm `assertNotNull` là đủ để test một method | Assertion phải xác nhận kết quả hoặc side effect thuộc hợp đồng |
| Exclude code khó test là cách giải quyết coverage thấp | Có thể che giấu vùng khó kiểm chứng; cần lý do và review rõ ràng |
| Chạy test pass chứng minh dependency bên ngoài hoạt động | Mock có thể không đi qua ranh giới thật; cần integration/contract test khi rủi ro yêu cầu |

## 20. Checklist đánh giá coverage có ý nghĩa

- Coverage report có đúng source set và test task mà CI chạy không?
- Dòng chưa cover có thuộc logic quan trọng hay chỉ là code không có hành vi đáng kể?
- Các nhánh thành công, từ chối, exception và fallback có test không?
- Assertion có xác nhận kết quả, trạng thái và side effect quan trọng không?
- Dữ liệu có bao gồm boundary và equivalence classes không?
- Các tổ hợp điều kiện có rủi ro tương tác đã được kiểm tra chưa?
- Module có impact cao có mức kiểm chứng phù hợp không?
- Có thể dùng mutation testing để đánh giá sức mạnh của assertion không?
- Test có ổn định và đủ nhanh để chạy trong CI không?
- Các exclusion có lý do rõ ràng và được review không?
- Ngưỡng coverage đang bảo vệ chất lượng hay chỉ khuyến khích tăng phần trăm?

Coverage dòng mã cho biết test đã thực thi phần nào của chương trình. Kiểm chứng hành vi cho biết hệ thống có làm đúng điều người dùng và thành phần khác mong đợi hay không. Đánh giá rủi ro giúp xác định hành vi nào cần được bảo vệ sâu nhất. Dùng cả ba góc nhìn sẽ tạo ra bộ test có giá trị hơn việc tối ưu một con số coverage đơn lẻ.
