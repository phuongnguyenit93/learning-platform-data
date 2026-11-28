# Coverage, mutation testing và đánh giá giá trị bộ kiểm thử

Trong Java 27, một dự án có thể đạt **95% line coverage** mà vẫn bỏ lọt lỗi quan trọng. Lý do là **đi qua một dòng mã** khác với **kiểm tra xem dòng mã đó có tạo ra kết quả đúng hay không**. Nếu một test chỉ gọi method và xác nhận không có ngoại lệ, nó có thể làm coverage tăng trong khi không phát hiện điều kiện sai, phép toán sai hoặc kết quả trả về sai.

**Mutation testing** bổ sung một góc nhìn khác: cố ý đưa những thay đổi nhỏ vào mã chương trình (gọi là **mutants**) rồi kiểm tra xem bộ test có phát hiện những thay đổi này không. Kết hợp kết quả coverage, mutation testing, kiểm thử theo yêu cầu nghiệp vụ và các tín hiệu thực tế như độ ổn định, tốc độ, khả năng chẩn đoán lỗi giúp đánh giá **giá trị của bộ kiểm thử**.

Bài học thuộc chương **Kiểm thử và chất lượng** của mô-đun **Java 27 và các kiến thức liên quan**. Nội dung tập trung vào cách tiếp cận còn áp dụng hiện nay: **JaCoCo** để đo coverage, **PIT/Pitest** cho mutation testing và **JUnit Jupiter** cho ví dụ test. Các framework này là công cụ ngoài JDK; cần lựa chọn phiên bản tương thích với Java 27 và hệ thống build.

## 1. Mục tiêu thực sự của một bộ kiểm thử

Bộ test có giá trị khi nó giúp nhóm phát triển:

- **Phát hiện sai lệch hành vi** so với yêu cầu, trước khi lỗi tới người dùng.
- **Bảo vệ quy tắc quan trọng** khi refactor hoặc nâng cấp Java/dependency.
- **Cung cấp phản hồi đáng tin cậy**, ít flaky và không phụ thuộc môi trường.
- **Chỉ ra lỗi ở đâu, vì sao** thông qua tên test và thông điệp assertion.
- **Chạy với chi phí chấp nhận được**, để nhóm sử dụng thường xuyên.
- **Kiểm chứng các rủi ro mà đo coverage thuần túy không quan sát được**, ví dụ integration, quyền truy cập, race condition, timeout hoặc dữ liệu lớn.

Các số đo coverage và mutation score là **tín hiệu hỗ trợ quyết định**, không phải mục đích cuối cùng. Một test có thể làm tăng tỷ lệ phần trăm nhưng không làm giảm rủi ro lỗi; ngược lại, một test tích hợp chứng minh quy trình thanh toán không tạo giao dịch trùng có thể rất có giá trị dù chỉ tăng chút ít coverage.

### 1.1. Hai câu hỏi cốt lõi

| Phép đo | Câu hỏi chính | Điều không trả lời được |
|---|---|---|
| **Code coverage** | Những phần mã nào đã được chạy khi test thực thi? | Kết quả có được kiểm chứng đúng hay không? |
| **Mutation testing** | Những thay đổi sai có mô phỏng được đã bị test phát hiện không? | Mọi lỗi thực tế, race hoặc lỗ hổng bảo mật đã bị chặn hết chưa? |

Vì vậy, **coverage cao không chứng minh test tốt**; **mutation score cao cũng không chứng minh phần mềm không có lỗi**.

## 2. Coverage đo điều gì?

**Code coverage** là mức độ mã được thực thi trong một bộ chạy kiểm thử. Công cụ Java phổ biến là **JaCoCo**, vốn thu thập coverage bằng cách instrument bytecode.

JaCoCo có nhiều loại counter. Những loại quan trọng:

| Chỉ số | Ý nghĩa | Thường được dùng để |
|---|---|---|
| **Instruction coverage (C0)** | Tỷ lệ lệnh bytecode được thực thi | Nhận diện mã hoàn toàn chưa chạy |
| **Branch coverage (C1)** | Tỷ lệ nhánh của các cấu trúc **if** và **switch** đã được thực thi | Phát hiện điều kiện chỉ được test một phía |
| **Line coverage** | Tỷ lệ dòng nguồn chứa lệnh đã được thực thi | Xem vùng mã bị bỏ qua khi đọc report |
| **Method coverage** | Method có ít nhất một lệnh được thực thi hay không | Nhận diện method chưa được gọi |
| **Class coverage** | Class có method nào được thực thi hay không | Phát hiện nhóm class chưa được test |
| **Complexity / missed complexity** | Độ phức tạp chu trình và phần chưa được coverage theo mô hình JaCoCo | Hỗ trợ tìm vùng logic quyết định cần test |

### 2.1. Instruction coverage

Công thức trực giác:

\[
\text{C0} = \frac{\text{lệnh bytecode đã được chạy}}{\text{tổng lệnh bytecode được đếm}}\times100\%
\]

Tỷ lệ này được tính trên **bytecode**, không phải số ký tự hoặc số dòng Java.

Một dòng Java có thể tạo nhiều lệnh JVM. Vì thế, **line coverage** và **instruction coverage** có thể khác nhau.

### 2.2. Branch coverage

Với câu lệnh:

~~~java
if (total >= 5_000) {
    fee = 0;
} else {
    fee = 600;
}
~~~

Nếu test chỉ chạy **total = 6_000**, nhánh **true** được chạy nhưng nhánh **false** chưa chạy. Dù dòng điều kiện được tính là đã đi qua, branch coverage mới thể hiện thiếu phía còn lại.

JaCoCo tính branch từ các cấu trúc **if** và **switch** ở mức bytecode. **Exception handling không được xem là branch trong định nghĩa C1 của JaCoCo**. Do đó, 100% branch coverage **không tự chứng minh** mọi cách ném và bắt ngoại lệ đã được kiểm tra.

### 2.3. Line coverage không đồng nghĩa kiểm tra đầy đủ điều kiện

~~~java
int result = enabled ? left + 1 : right - 1;
~~~

Một dòng có thể bao gồm nhiều hành vi. Khi một nhánh đã chạy, dòng có thể được tính là covered, trong khi nhánh còn lại vẫn chưa được kiểm tra.

Ngoài ra, bytecode do compiler tạo, các phương thức tổng hợp và cơ chế lọc do JaCoCo cung cấp có thể khiến tỷ lệ đo được khác với số dòng Java nhìn thấy trong editor.

### 2.4. Coverage không phải path coverage

Giả sử có ba điều kiện **if** độc lập. Branch coverage có thể đạt 100% khi từng phía true/false đã xuất hiện, nhưng chưa chắc đã kiểm tra đủ mọi **tổ hợp điều kiện**.

Ví dụ:

~~~java
if (vip) {
    discount += 10;
}

if (weekend) {
    discount += 5;
}

if (couponValid) {
    discount += 15;
}
~~~

Có thể tồn tại những lỗi chỉ xuất hiện khi **vip = true**, **weekend = true** và **couponValid = true** cùng lúc, dù từng điều kiện đã được test riêng.

Cần kết hợp coverage với **decision tables, boundary testing, pairwise/combinatorial testing** hoặc kiểm thử theo quy tắc nghiệp vụ phù hợp.

## 3. Coverage cao nhưng assertion yếu: một ví dụ

Xét yêu cầu tính phí vận chuyển:

- Giỏ hàng có giá trị **âm** là dữ liệu không hợp lệ.
- Nếu tổng giỏ hàng **từ 5.000 cents trở lên**, phí cơ bản là **0**.
- Nếu tổng giỏ hàng **dưới 5.000 cents**, phí cơ bản là **600 cents**.
- Nếu chọn giao nhanh (**express**), cộng thêm **250 cents**.

Trong bài này dùng **int cents**, không dùng **double** để tính tiền nhỏ. Với hệ thống tài chính thực tế, cần xem thêm tiền tệ, giới hạn số và **BigDecimal** khi có phần thập phân/quy tắc tính phức tạp.

### 3.1. Mã sản phẩm

Lưu **ShippingPolicy.java**:

~~~java
package example;

public final class ShippingPolicy {

    private ShippingPolicy() {}

    public static int feeCents(
            int subtotalCents,
            boolean express
    ) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                "subtotalCents must not be negative"
            );
        }

        int baseFee = subtotalCents >= 5_000 ? 0 : 600;

        return express ? baseFee + 250 : baseFee;
    }
}
~~~

Một số trường hợp:

| Subtotal (cents) | Express? | Phí mong đợi (cents) | Giải thích |
|---:|---|---:|---|
| -1 | false | Ngoại lệ | Dữ liệu sai |
| 0 | false | 600 | Không đạt ngưỡng miễn phí |
| 4.999 | false | 600 | Dưới ngưỡng đúng 1 cent |
| 5.000 | false | 0 | Đúng ngưỡng được miễn phí cơ bản |
| 5.001 | false | 0 | Trên ngưỡng |
| 4.999 | true | 850 | 600 + 250 |
| 5.000 | true | 250 | 0 + 250 |

### 3.2. Một bộ test chạm nhiều nhánh nhưng không kiểm tra phí

Lưu ý: đoạn sau dùng **JUnit Jupiter**; thư viện JUnit cần được cấu hình trong hệ thống build của dự án.

~~~java
package example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class WeakShippingPolicyTest {

    @Test
    void executesBranchesButDoesNotVerifyPrices() {
        assertDoesNotThrow(
            () -> ShippingPolicy.feeCents(0, false)
        );

        assertDoesNotThrow(
            () -> ShippingPolicy.feeCents(5_000, false)
        );

        assertDoesNotThrow(
            () -> ShippingPolicy.feeCents(0, true)
        );

        assertDoesNotThrow(
            () -> ShippingPolicy.feeCents(5_000, true)
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> ShippingPolicy.feeCents(-1, false)
        );
    }
}
~~~

Test đã đi qua nhiều đường thực thi, trong đó có cả hai phía của điều kiện ngưỡng và hai giá trị **express**. Nhưng nó **không kiểm tra giá trị phí trả về**.

Nếu lỗi làm phí giao nhanh tăng từ 250 lên 900 cents, test vẫn có thể **PASS** vì tất cả lời gọi đều không ném exception.

Đây là một minh họa điển hình cho vấn đề **coverage cao nhưng oracle yếu**.

**Test oracle** là cơ sở quyết định kết quả có đúng không. Trong ví dụ, oracle là phí chính xác theo quy tắc nghiệp vụ; **assertDoesNotThrow** chỉ kiểm tra một phần nhỏ của hợp đồng.

## 4. Viết test có oracle mạnh và ranh giới rõ ràng

Thay bằng các assertion biểu đạt kỳ vọng cụ thể.

Lưu **ShippingPolicyTest.java**:

~~~java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingPolicyTest {

    @Test
    void zeroSubtotalPaysBasicFee() {
        assertEquals(
            600,
            ShippingPolicy.feeCents(0, false)
        );
    }

    @Test
    void oneCentBelowThresholdPaysBasicFee() {
        assertEquals(
            600,
            ShippingPolicy.feeCents(4_999, false)
        );
    }

    @Test
    void exactlyAtThresholdGetsFreeBasicShipping() {
        assertEquals(
            0,
            ShippingPolicy.feeCents(5_000, false)
        );
    }

    @Test
    void oneCentAboveThresholdStillGetsFreeShipping() {
        assertEquals(
            0,
            ShippingPolicy.feeCents(5_001, false)
        );
    }

    @Test
    void expressBelowThresholdAddsSurcharge() {
        assertEquals(
            850,
            ShippingPolicy.feeCents(4_999, true)
        );
    }

    @Test
    void expressAtThresholdStillPaysOnlySurcharge() {
        assertEquals(
            250,
            ShippingPolicy.feeCents(5_000, true)
        );
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(
            IllegalArgumentException.class,
            () -> ShippingPolicy.feeCents(-1, false)
        );
    }
}
~~~

Hai test **4.999** và **5.000** đặc biệt quan trọng: chúng phân biệt toán tử **>=** với **>** tại điểm bằng ngưỡng.

### 4.1. Vì sao cần cả trước, đúng và sau ranh giới?

Với điều kiện **subtotal >= 5_000**, ba giá trị nên được kiểm tra:

- **4.999**: trước ngưỡng.
- **5.000**: đúng ngưỡng.
- **5.001**: sau ngưỡng.

Nếu chỉ dùng 4.000 và 6.000, một bug thay **>=** thành **>** có thể hoàn toàn không bị phát hiện.

### 4.2. Vì sao test phải độc lập?

Mỗi test nên tự thiết lập đầu vào, không phụ thuộc method test khác được chạy trước đó. Trong ví dụ, **ShippingPolicy.feeCents** là hàm thuần: cùng đầu vào luôn cho cùng kết quả hoặc cùng ngoại lệ, không có file, mạng, DB hay đồng hồ hệ thống.

Những đặc tính này giúp bộ test:

- Lặp lại dễ dàng.
- Chạy song song an toàn hơn.
- Tái hiện mutant survived.
- Không cần các thao tác setup/teardown đắt tiền.

## 5. Mutation testing là gì?

**Mutation testing** cố ý tạo những biến thể nhỏ của mã đã biên dịch, ví dụ:

- Đổi toán tử điều kiện **>=** thành **>**.
- Đảo điều kiện **==** thành **!=**.
- Đổi phép toán **+** thành **-**.
- Thay kết quả trả về thành giá trị mặc định khác.
- Bỏ một lời gọi method có tác dụng phụ theo những mutator tương ứng.

Mỗi biến thể là một **mutant**. Công cụ chạy những test liên quan trên mutant đó và quan sát liệu bộ test có báo lỗi hay không.

~~~mermaid
flowchart TD
    A["Bản gốc: source + tests đều PASS"]
    B["Mutation engine tạo một mutant"]
    C["Chạy tests liên quan trên mutant"]
    D{"Test có thất bại?"}
    E["KILLED — phát hiện thay đổi"]
    F["SURVIVED — chưa phát hiện"]
    G["Phân tích survivor / thêm test"]
    H["Tiếp tục mutant kế tiếp"]
    A --> B --> C --> D
    D -->|"Có"| E --> H
    D -->|"Không"| F --> G --> H
~~~

Thường mỗi mutant chỉ đưa vào **một thay đổi tại một vị trí**. Mục tiêu là xác định những thay đổi đủ gần lỗi thật mà test nên phát hiện.

### 5.1. PIT/Pitest làm gì trong hệ sinh thái Java?

**PIT** là công cụ mutation testing phổ biến trên JVM:

1. Phân tích bytecode từ chương trình.
2. Tạo mutants bằng các *mutators* đã cấu hình.
3. Xác định những test có khả năng thực thi vùng mã đó.
4. Chạy test tương ứng trên mutant.
5. Báo mutant bị phát hiện, còn sống hoặc không được test bao phủ.

PIT làm việc ở mức **bytecode**, vì vậy tên và cách mô tả mutant trong report có thể không trùng 1:1 với một phép sửa mã nguồn Java nhìn thấy.

**PIT không thuộc Java SE 27**; cần cài plugin/build integration thích hợp và xác minh phiên bản hỗ trợ bytecode do JDK 27 tạo ra.

## 6. Ví dụ một mutant bị phát hiện

Bản gốc:

~~~java
int baseFee = subtotalCents >= 5_000 ? 0 : 600;
~~~

Một mutation tại ranh giới có thể tương đương với:

~~~java
int baseFee = subtotalCents > 5_000 ? 0 : 600;
~~~

Với **subtotalCents = 5_000**:

| Phiên bản | Kết quả phí cơ bản |
|---|---:|
| Bản gốc **>=** | 0 |
| Mutant **>** | 600 |

Test:

~~~java
assertEquals(0, ShippingPolicy.feeCents(5_000, false));
~~~

sẽ PASS trên bản gốc và FAIL trên mutant. Mutant được **killed**.

### 6.1. Một mutant làm sai express surcharge

Bản gốc:

~~~java
return express ? baseFee + 250 : baseFee;
~~~

Một thay đổi sai (minh họa):

~~~java
return express ? baseFee - 250 : baseFee;
~~~

Test:

~~~java
assertEquals(850, ShippingPolicy.feeCents(4_999, true));
~~~

sẽ phát hiện khác biệt vì bản sai tạo kết quả **350**, không phải **850**.

Cần phân biệt **mutation giả định để giảng giải** với danh sách mutant chắc chắn được một bản PIT tạo ra. Những biến đổi thực tế phụ thuộc tập mutators, bytecode và bộ lọc mà công cụ dùng.

## 7. Mutant survived là một tín hiệu cần điều tra

Nếu mutant vẫn làm toàn bộ test PASS, công cụ báo **SURVIVED**. Những lý do thường gặp:

1. Test đã chạy dòng mã nhưng **không assert giá trị phù hợp**.
2. Test chỉ dùng dữ liệu “bình thường” và **không chạm ranh giới**.
3. Test kiểm tra mock interaction nhưng **bỏ qua kết quả nghiệp vụ**.
4. Code có nhiều nhánh, nhưng tổ hợp đầu vào gây khác biệt chưa được test.
5. Mutant tương đương về mặt quan sát trong miền đầu vào hợp lệ.
6. Mutant nằm ở mã không mang ý nghĩa nghiệp vụ hoặc được lọc chưa hợp lý.
7. Test có lỗi thiết kế, dùng kỳ vọng rút ra từ chính implementation.

Một survivor **không tự chứng minh thiếu test hợp lệ**. Cần xem:

- Dòng/bytecode nào bị biến đổi?
- Tại input nào bản gốc và mutant có thể cho kết quả khác nhau?
- Khác biệt có thuộc hợp đồng nghiệp vụ không?
- Nếu thuộc hợp đồng, nên bổ sung assertion/test nào?
- Nếu không thể phân biệt bằng bất kỳ hành vi hợp lệ nào, có thể là **equivalent mutant**.

## 8. Equivalent mutants: giới hạn quan trọng

Một **equivalent mutant** có hành vi quan sát được tương đương bản gốc trên **mọi đầu vào hợp lệ** theo hợp đồng hệ thống.

Ví dụ khái niệm:

~~~java
int result = value + 0;
~~~

Thay thành:

~~~java
int result = value;
~~~

thì hai biểu thức tương đương với mọi giá trị **int** trong ngữ cảnh đơn giản đó. Không có test đúng nào phân biệt chúng chỉ bằng đầu vào/đầu ra.

Trong thực tế, việc chứng minh tương đương cho mã bất kỳ rất khó. Vì vậy:

- Không cố viết test vô nghĩa chỉ để “kill” một mutant có vẻ tương đương.
- Không mặc nhiên phân loại mọi survivor là equivalent.
- Ghi lại chứng cứ: miền đầu vào, hợp đồng, side effects, overflow, ngoại lệ và concurrency.
- Áp dụng loại trừ/chính sách tương ứng với công cụ chỉ sau khi review, có ghi nhận minh bạch.

Một số mutation operators được công cụ lựa chọn để **giảm** việc sinh ra mutant tương đương, nhưng không thể loại bỏ hoàn toàn vấn đề này.

## 9. Các trạng thái trong báo cáo mutation testing

Tên cụ thể có thể thay đổi theo công cụ/phiên bản. Với PIT, thường gặp:

| Trạng thái | Ý nghĩa | Hướng phân tích |
|---|---|---|
| **KILLED** | Test phát hiện biến đổi | Kiểm tra test fail vì đúng hành vi bị biến đổi |
| **SURVIVED** | Test được chạy nhưng chưa phát hiện mutant | Thêm/chỉnh test nếu có khác biệt đáng kiểm tra |
| **NO_COVERAGE** | Không tìm thấy test thực thi vùng mutant | Bổ sung test cho vùng chưa được chạm |
| **TIMED_OUT** | Test trên mutant không hoàn thành trong ngưỡng | Xem có tạo vòng lặp vô hạn hay timeout bất thường |
| **NON_VIABLE** | Mutant không thể chạy hợp lệ hoặc có vấn đề về bytecode | Không coi tương đương với lỗi bị test phát hiện |
| **RUN_ERROR / MEMORY_ERROR** | Có lỗi khi chạy hoặc tài nguyên không đủ | Kiểm tra môi trường, classpath, memory, test setup |

Một mutant bị **TIMED_OUT** có thể do thay đổi tạo vòng lặp không kết thúc, nhưng cũng có thể là dấu hiệu của test chậm/flaky hoặc cấu hình timeout chưa hợp lý. Không nên gộp mọi timeout vào “test chất lượng cao” nếu không điều tra.

### 9.1. Không nhầm NO_COVERAGE với SURVIVED

- **NO_COVERAGE**: chưa có test phù hợp chạy tới mã đó.
- **SURVIVED**: test đã đi qua mã, nhưng không phân biệt được bản gốc và bản biến đổi.

Đây là hai hướng cải thiện khác nhau: **bổ sung test bao phủ** và **tăng chất lượng oracle/dữ liệu đầu vào**.

## 10. Mutation score và test strength

Một cách diễn giải phổ biến:

\[
\text{Mutation score} =
\frac{\text{KILLED}}{\text{Tổng mutants hợp lệ được tính vào score}}
\times100\%
\]

Với cách tổng hợp minh họa có **KILLED = K**, **SURVIVED = S**, **NO_COVERAGE = N** và những trạng thái khác được xử lý theo chính sách công cụ:

\[
\text{Mutation score ví dụ} =
\frac{K}{K+S+N}\times100\%
\]

PIT còn phân biệt **test strength** — khả năng phát hiện trong số mutants đã có thông tin coverage:

\[
\text{Test strength} =
\frac{K}{K+S}\times100\%
\]

Những công thức trên chỉ đúng khi phạm vi trạng thái/điều kiện đếm khớp cấu hình báo cáo. Cần đọc định nghĩa của công cụ/phiên bản trước khi so sánh giữa các dự án.

### 10.1. Ví dụ với số liệu

Giả sử báo cáo có:

| Trạng thái | Số mutant |
|---|---:|
| KILLED | 36 |
| SURVIVED | 9 |
| NO_COVERAGE | 5 |
| Tổng ba nhóm | 50 |

Khi đó:

- **Mutation score minh họa**: **36 / 50 = 72%**.
- **Test strength**: **36 / (36 + 9) = 80%**.

Tập test có khả năng phát hiện khá nhiều mutants nó đã đi qua, nhưng vẫn còn **5 mutants không có coverage** và **9 mutants có coverage nhưng sống sót**.

### 10.2. Điểm số cao nhưng chưa chắc đủ an toàn

Một module có 95% mutation score vẫn có thể chứa một lỗi nghiêm trọng ở logic:

- Kiểm tra quyền truy cập.
- Tính tiền hoặc làm tròn.
- Ngăn duplicate payment.
- Cập nhật trạng thái giao dịch.
- Giải quyết race condition.

Bộ mutators mặc định cũng không mô phỏng được mọi kiểu lỗi. Vì thế, không dùng điểm số mutation như giấy chứng nhận “đã test hết”.

## 11. Code coverage và mutation testing bổ sung nhau

| Kết hợp | Nhận định | Hành động ưu tiên |
|---|---|---|
| Coverage thấp, mutation thấp | Nhiều vùng chưa được test hoặc không có oracle | Test theo rủi ro, bao phủ luồng quan trọng |
| Coverage cao, mutation thấp | Code chạy nhưng assertions/biên có thể yếu | Xem mutants sống sót, kiểm tra oracle |
| Coverage thấp, mutation cao trên phạm vi nhỏ | Các vùng đã test kỹ nhưng phạm vi hẹp | Mở rộng phạm vi test có mục tiêu |
| Coverage cao, mutation cao | Tín hiệu tốt trên mã được đo | Tiếp tục kiểm tra integration, security, concurrency |
| Coverage tăng, mutation không đổi | Có thể chỉ thêm test đi qua code | Xem assertion và dữ liệu test |
| Coverage giữ nguyên, mutation tăng | Test phát hiện thêm lỗi tại cùng vùng code | Thường là cải thiện đáng chú ý |

**Không xếp hạng chất lượng nhóm hoặc cá nhân chỉ bằng một con số coverage/mutation.** Số đo phụ thuộc phạm vi, loại phần mềm, cấu hình exclude, độ phức tạp và các rủi ro mà công cụ có thể mô phỏng.

## 12. JaCoCo trên Java 27: cách cấu hình và diễn giải

**JaCoCo 0.8.16**, phát hành tháng **10/2026**, có hỗ trợ chính thức **Java 27**. Khi biên dịch bằng **javac --release 27** hoặc bytecode Java 27, hãy dùng JaCoCo và hệ thống build hỗ trợ định dạng class file tương ứng.

Một lỗi do tool không hiểu bytecode Java mới **không phải** bằng chứng test không bao phủ mã.

### 12.1. Ví dụ Gradle Groovy DSL

Các đoạn cấu hình sau là **minh họa** cho một dự án Gradle dùng **java** và **jacoco** plugins, có dependency JUnit Jupiter tương thích đã được cấu hình:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}

jacoco {
    toolVersion = '0.8.16'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')

    reports {
        html.required = true
        xml.required = true
    }
}
~~~

Các lệnh thường dùng của một dự án Gradle có wrapper:

~~~bash
./gradlew test jacocoTestReport
~~~

Nếu dùng Windows PowerShell:

~~~powershell
.\gradlew.bat test jacocoTestReport
~~~

**Các lệnh chỉ là hướng dẫn**, không được chạy trong quá trình tạo bài học này.

Cần bảo đảm test task thực sự chạy và JaCoCo agent thu thập dữ liệu đúng. Nếu dự án có **nhiều test tasks** (unit/integration), cần cấu hình collection/report riêng hoặc aggregation có chủ đích.

### 12.2. Ví dụ JaCoCo Maven

Với Maven, có thể gắn **prepare-agent** trước khi chạy test và **report** sau đó:

~~~xml
<plugin>
  <groupId>org.jacoco</groupId>
  <artifactId>jacoco-maven-plugin</artifactId>
  <version>0.8.16</version>
  <executions>
    <execution>
      <goals>
        <goal>prepare-agent</goal>
      </goals>
    </execution>
    <execution>
      <id>report</id>
      <phase>verify</phase>
      <goals>
        <goal>report</goal>
      </goals>
    </execution>
  </executions>
</plugin>
~~~

Chèn trong **build/plugins** của **pom.xml** và chạy một vòng Maven tương ứng:

~~~bash
mvn verify
~~~

Tùy cấu hình, test task chạy bởi **maven-surefire-plugin** hoặc Failsafe. Nếu bạn tự cấu hình **argLine**, cần bảo đảm không ghi đè mất Java agent arguments do JaCoCo thiết lập.

**Không** tự giả định báo cáo unit tests đã bao phủ integration tests nếu chúng chạy ở một JVM khác mà agent không được gắn.

### 12.3. Đọc report JaCoCo theo thứ tự

1. Kiểm tra **tests có thực sự chạy** (không bị skip).
2. Mở report HTML hoặc XML.
3. Xem package/class/method có **missed lines** và **missed branches**.
4. Tìm những điều kiện quan trọng chỉ được test một phía.
5. Đọc lại test assertions, không kết luận từ màu xanh.
6. Xác minh mã generated/instrumented có được lọc đúng mà không làm ẩn logic sản phẩm.

### 12.4. Vì sao một dòng có thể không được đánh dấu covered dù chạy tới đó?

JaCoCo sử dụng probes trong control flow. Nếu một ngoại lệ cắt ngang trước khi probe tiếp theo được ghi nhận, một số dòng có thể hiển thị thiếu coverage dù người phát triển quan sát rằng luồng thực thi đi vào gần đó.

Ngoài ra, **line coverage** cần class files có thông tin line numbers; nếu build loại bỏ debug metadata, báo cáo có thể thiếu chi tiết dòng nguồn.

Không tự ý sửa test chỉ để tô xanh một dòng nếu đó là giới hạn instrument/probe và không liên quan tới hành vi cần bảo vệ.

## 13. PIT trên Java 27: quy trình chạy an toàn

Để dùng PIT trong một dự án:

1. Chọn phiên bản PIT cùng Maven/Gradle integration tương thích với JDK và **class file Java 27**.
2. Chọn test framework adapter thích hợp; với **JUnit Jupiter** cần xác nhận plugin/engine integration tương ứng.
3. Đảm bảo test gốc chạy **ổn định và PASS**.
4. Thu hẹp phạm vi ban đầu vào một package/service có ý nghĩa.
5. Chạy mutation analysis và kiểm tra kết quả.
6. Phân tích survivors theo từng hành vi, không “sửa điểm số” bằng exclude vô tội vạ.
7. Mở rộng dần phạm vi khi chi phí đã được đo.

### 13.1. Lệnh PIT Maven

Sau khi cấu hình **pitest-maven** và adapter cần thiết, có thể chạy:

~~~bash
mvn test-compile org.pitest:pitest-maven:mutationCoverage
~~~

Báo cáo HTML thường nằm dưới **target/pit-reports/** theo cấu hình và phiên bản.

Không copy cấu hình có **version=LATEST** từ tài liệu quickstart cũ vào production build. Nên **pin phiên bản được dự án kiểm chứng**, sau đó nâng cấp có kiểm soát.

### 13.2. Cấu hình phạm vi

Trong PIT Maven, **targetClasses** và **targetTests** giúp tập trung vào vùng muốn phân tích.

Ví dụ một phần cấu hình:

~~~xml
<configuration>
  <targetClasses>
    <param>example.ShippingPolicy*</param>
  </targetClasses>
  <targetTests>
    <param>example.*Test</param>
  </targetTests>
</configuration>
~~~

Đoạn này là phần cấu hình đặt bên trong **pitest-maven** plugin đã chọn version tương thích. Nó không phải **pom.xml** hoàn chỉnh.

Khi giới hạn targetClasses, phải chắc chắn class/record hoặc nested classes liên quan không vô tình bị loại khỏi phạm vi. Nếu report không có mutants, hãy kiểm tra target filters, test discovery và compiled classes trước khi kết luận test tốt.

### 13.3. Mutators nên bắt đầu thế nào?

Một số nhóm điển hình của PIT:

- **CONDITIONALS_BOUNDARY**: đổi **<** thành **<=**, **>=** thành **>**, v.v.
- **NEGATE_CONDITIONALS**: đảo điều kiện.
- **MATH**: thay toán tử số học tương ứng.
- **VOID_METHOD_CALLS**: bỏ lời gọi method trả **void**.
- **Các mutator thay return value**: đổi kết quả boolean, số, null hoặc empty theo loại.

Bắt đầu từ tập **DEFAULTS** của phiên bản đang dùng. Không bật tất cả mutators ngay khi chưa hiểu số lượng/equivalent mutants và chi phí.

**Tên mutator và nhóm mặc định có thể thay đổi theo phiên bản**; đọc report thực tế và tài liệu của công cụ được pin trong build.

### 13.4. Không chạy PIT khi test suite còn flaky

Mutation testing thường chạy test nhiều lần trên những biến thể khác nhau. Nếu test thỉnh thoảng fail trên **mã gốc**, bạn sẽ nhận nhiều kết quả gây nhiễu, timeout hoặc mutant bị “kill” vì lý do ngoài thay đổi đang kiểm tra.

Trước tiên ổn định tests, đặc biệt với test phụ thuộc:

- Giờ hệ thống.
- Random không có seed.
- HTTP bên ngoài.
- Database dùng chung.
- Thứ tự chạy và dữ liệu tĩnh.
- Race condition.
- Sleep hoặc timeout quá sát ngưỡng.

## 14. Cách phân tích một survivor có ích

Giả sử report nêu một mutant tại điều kiện:

~~~java
subtotalCents >= 5_000
~~~

Báo **SURVIVED** khi đổi thành **>**.

Quy trình:

1. Xem điều kiện gốc và mutant.
2. Tìm đầu vào tạo khác biệt: **subtotalCents = 5_000**.
3. Xác định kết quả đúng từ hợp đồng: **phí cơ bản = 0**.
4. Kiểm tra test hiện tại đã dùng input này chưa.
5. Nếu chưa có, thêm test ranh giới với **assertEquals(0, ...)**.
6. Nếu có nhưng survivor vẫn sống, kiểm tra assertion hoặc report/filter.
7. Chạy lại test gốc rồi mutation testing.

### 14.1. Bảng điều tra survivors

| Survivor | Khả năng thiếu sót | Test nên cân nhắc |
|---|---|---|
| **>=** đổi thành **>** | Thiếu đúng ngưỡng | Test input bằng threshold |
| **+250** đổi thành phép toán khác | Thiếu oracle giá trị express | Assert chính xác fee khi express |
| Return boolean bị đổi | Chỉ assert không ném exception | Assert true/false theo hợp đồng |
| Bỏ lời gọi ghi audit | Chỉ kiểm tra kết quả, không kiểm tra side effect bắt buộc | Kiểm tra audit/event có tồn tại |
| Đổi xử lý null | Thiếu null/invalid input | Assert loại lỗi hoặc fallback đúng |
| Đổi điều kiện quyền truy cập | Thiếu dữ liệu role/permission biên | Test denied/allowed theo ma trận |
| Mutant trong code không được gọi | Test target sai hoặc feature chưa test | Bổ sung test/rà soát phạm vi |
| Mutant dường như tương đương | Không có input hợp lệ tạo khác biệt | Review bằng chứng và ghi nhận |

**Không nên** viết một test chỉ biết đến chi tiết bytecode mutant mà bỏ qua hợp đồng sản phẩm. Chọn case vì nó biểu thị một **rủi ro nghiệp vụ có thật**.

## 15. Rủi ro “test oracle trùng implementation”

Một dạng test yếu là tính expected bằng chính logic giống hệt production code.

Ví dụ cần kiểm tra phép tính:

~~~java
int actual = ShippingPolicy.feeCents(subtotal, express);

int expected = subtotal >= 5_000
    ? (express ? 250 : 0)
    : (express ? 850 : 600);
~~~

Cách này có thể tạm đủ trong ví dụ đơn giản, nhưng nếu code production và expected cùng sao chép một **giả định sai**, test sẽ củng cố lỗi đó.

Oracle mạnh hơn thường lấy từ:

- Yêu cầu nghiệp vụ độc lập.
- Bảng quyết định đã được review.
- Ví dụ được chấp thuận với expected value cụ thể.
- Một mô hình đơn giản có triển khai độc lập.
- Các thuộc tính bất biến (*invariants*) của miền nghiệp vụ.
- Dữ liệu chuẩn đã được xác thực (*golden fixtures*) khi phù hợp.

Không dùng **snapshot** tùy tiện làm nguồn chân lý duy nhất nếu snapshot được sinh từ chính implementation sai mà không qua review.

## 16. Parameterized tests và decision tables

Để xem rõ nhiều trường hợp, dùng **@ParameterizedTest** của JUnit Jupiter với **@CsvSource**.

~~~java
package example;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ShippingPolicyTableTest {

    @ParameterizedTest
    @CsvSource({
        "0, false, 600",
        "4999, false, 600",
        "5000, false, 0",
        "5001, false, 0",
        "4999, true, 850",
        "5000, true, 250",
        "5001, true, 250"
    })
    void shippingFeeFollowsBusinessRule(
            int subtotal,
            boolean express,
            int expected
    ) {
        assertEquals(
            expected,
            ShippingPolicy.feeCents(subtotal, express)
        );
    }
}
~~~

Tính năng này cần dependency **junit-jupiter-params** cùng phiên bản JUnit Jupiter tương thích với dự án.

### 16.1. Không nhầm nhiều rows với độ bao phủ tốt

Một bảng có 1.000 dòng nhưng chỉ kiểm tra những giá trị 6.000, 7.000, 8.000 vẫn không phát hiện bug **>=** thành **>** tại 5.000.

**Chất lượng phân hoạch dữ liệu** quan trọng hơn số lượng hàng.

Các phân hoạch nên cân nhắc:

- Hợp lệ và không hợp lệ.
- Đúng ranh giới, ngay trước, ngay sau.
- Null/empty nếu hợp đồng cho phép.
- Giá trị rất lớn, giới hạn số nguyên, overflow.
- Tổ hợp điều kiện quan trọng.
- Những trạng thái side effect hoặc lỗi dependency.

## 17. Property-based và metamorphic testing

Một số tính chất của hàm có thể kiểm tra trên nhiều đầu vào mà không phải liệt kê toàn bộ expected values.

Với **ShippingPolicy**:

1. Phí không âm với subtotal hợp lệ.
2. Giao nhanh đắt hơn giao thường đúng **250 cents** với cùng subtotal.
3. Phí giao thường không tăng khi subtotal tăng từ 0 lên một giá trị lớn hơn.
4. Phí cơ bản bằng 0 khi subtotal từ 5.000 trở lên.

Ví dụ test kiểu property với vòng lặp xác định:

~~~java
package example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShippingPolicyPropertyTest {

    @Test
    void expressAddsExactlyTwoHundredFiftyCents() {
        for (int subtotal = 0; subtotal <= 20_000;
                subtotal += 137) {

            int standard =
                ShippingPolicy.feeCents(subtotal, false);

            int express =
                ShippingPolicy.feeCents(subtotal, true);

            assertEquals(250, express - standard);
            assertTrue(standard >= 0);
        }
    }
}
~~~

Đây là **kiểm tra một tập mẫu có chọn lọc**, không phải chứng minh toán học mọi số nguyên. Một thư viện property-based testing có thể tự sinh nhiều dữ liệu và thu nhỏ (*shrinking*) ví dụ khi thất bại.

**Metamorphic testing** cũng hữu ích khi khó biết kết quả chính xác nhưng biết quan hệ giữa hai lần chạy. Ví dụ cùng subtotal, bật express phải tăng phí đúng 250 cents. Tuy nhiên, quan hệ này chỉ hợp lệ nếu nó thực sự có trong hợp đồng nghiệp vụ.

## 18. Mutation testing cần test có tính xác định

Một mutant chỉ có ý nghĩa khi kết quả test có thể tái hiện.

### 18.1. Thời gian

Không viết:

~~~java
assertTrue(
    token.expiresAt().isAfter(java.time.Instant.now())
);
~~~

nếu test phụ thuộc ngưỡng thời gian có thể trôi qua bất ngờ.

Ưu tiên Clock injection:

~~~java
var clock = java.time.Clock.fixed(
    java.time.Instant.parse("2026-11-27T10:00:00Z"),
    java.time.ZoneOffset.UTC
);
~~~

Từ một Clock cố định, test các mốc trước/đúng/sau hạn mà không chờ thời gian thực.

### 18.2. Random

Nếu logic dùng random, đặt seed hoặc inject nguồn random theo hợp đồng. Với bảo mật, **không** thay production cryptographic random bằng một seed cố định; chỉ giả lập/điều khiển trong kiểm thử có phạm vi rõ.

### 18.3. I/O ngoài hệ thống

Không phụ thuộc một website công khai luôn trả 200, một database chung luôn chứa cùng dữ liệu hoặc độ trễ mạng luôn dưới 10 ms.

Dùng mock/test double khi cần unit test nhanh, và một HTTP/DB test environment được kiểm soát để xác nhận hợp đồng tích hợp.

### 18.4. Concurrency

Test race condition không thể chỉ “sleep một chút rồi hy vọng”. Dùng barrier, latch, event trace hoặc công cụ kiểm thử concurrency phù hợp. PIT mặc định cũng không có khả năng chứng minh không còn mọi race condition.

## 19. Coverage và mutation chưa đủ cho các loại test khác

Một bộ test có thể đạt chỉ số tốt ở unit level nhưng thiếu:

- **Integration tests**: phối hợp giữa service, database, HTTP client/server.
- **Contract tests**: giữ hợp đồng giữa producer và consumer API.
- **End-to-end tests**: đường đi nghiệp vụ quan trọng.
- **Security tests**: authorization, input validation, secret handling.
- **Performance tests**: throughput, tail latency, allocation/GC, contention.
- **Resilience tests**: timeout, retry, cancellation, partial failure.
- **Concurrency tests**: race, deadlock, ordering, visibility.
- **Schema/migration tests**: tương thích dữ liệu giữa phiên bản.

Mutation operators phổ biến chủ yếu tác động lên logic mức lệnh/phương thức. **Không có cam kết** rằng chúng đại diện cho network partition, race condition, sai IAM policy hay dữ liệu bị mất sau crash.

**Test portfolio** tốt sử dụng nhiều cấp độ kiểm thử, mỗi cấp giải quyết một nhóm rủi ro.

## 20. Giá trị bộ test không chỉ nằm ở tỷ lệ phần trăm

Có thể đánh giá theo những chiều sau:

| Chiều đánh giá | Tín hiệu tích cực | Dấu hiệu rủi ro |
|---|---|---|
| **Phạm vi** | Các luồng và ranh giới quan trọng có test | Những module quan trọng chưa được test |
| **Khả năng phát hiện lỗi** | Mutants có ý nghĩa bị killed, assertions cụ thể | Mutants survived dù line covered |
| **Ổn định** | Lặp lại nhiều lần cho kết quả nhất quán | Flaky, lệ thuộc ngày/giờ/mạng |
| **Tốc độ phản hồi** | Test cấp thấp chạy nhanh, PR feedback sớm | Toàn bộ suite mất quá lâu |
| **Khả năng chẩn đoán** | Tên test và failure message chỉ ra quy tắc bị vi phạm | Test thất bại nhưng không rõ vì sao |
| **Độc lập** | Không phụ thuộc thứ tự/đồng bộ trạng thái ngầm | Chỉ pass khi chạy theo thứ tự nhất định |
| **Dễ bảo trì** | Test theo hợp đồng, ít kiểm tra cấu trúc nội bộ | Refactor đúng vẫn làm test vỡ hàng loạt |
| **Chi phí** | Có CI, tài nguyên cân đối | Mutation/full-suite quá đắt để chạy thường xuyên |
| **Rủi ro sản phẩm** | Chặn lỗi ở quyền, tiền, dữ liệu, tương thích | Chỉ tập trung test những hàm dễ test |
| **Tín hiệu thực tế** | Ít regression thoát qua CI và có phân tích nguyên nhân | Production bugs thường lặp lại cùng dạng |

### 20.1. Không lấy số lượng test làm KPI đơn lẻ

100 test chỉ gọi getter có thể kém giá trị hơn 10 test xác minh đúng một thuật toán định giá phức tạp.

### 20.2. Không lấy mutation score làm chỉ số năng suất cá nhân

Điểm số bị ảnh hưởng bởi code generated, tập mutators, độ phức tạp và khả năng test. Nếu biến thành chỉ tiêu thưởng/phạt, nhóm có thể thêm test vô nghĩa hoặc exclude mã quan trọng để “đẹp report”.

Nên dùng số liệu để **chỉ dẫn điều tra và cải thiện rủi ro**, không thay thế đánh giá kỹ thuật.

## 21. Test value theo rủi ro nghiệp vụ

Một cách ưu tiên thực tế:

| Khu vực | Rủi ro nếu sai | Loại test có giá trị |
|---|---|---|
| Thanh toán | Tính sai tiền, giao dịch trùng | Boundary, invariant, idempotency, integration |
| Phân quyền | Lộ dữ liệu, cấp quyền sai | Positive/negative permission matrix, security tests |
| Tính phí | Sai tại ranh giới | Decision table, mutation condition boundary |
| Đồng bộ dữ liệu | Mất/nhân bản dữ liệu | Contract, retry/failure recovery, integration |
| Ngày/giờ | Sai chuyển ngày/múi giờ | Fixed Clock, zone/DST boundary |
| Cache | Stale data, thiếu invalidation | Expiry/invalidation, concurrency, integration |
| API parsing | Null, empty, malformed inputs | Parameterized tests, fuzz/property tests |
| Logging/metric formatting | Sai thông tin quan sát | Test vừa đủ theo mức tác động, tránh lạm dụng |

Khi thời gian hạn chế, ưu tiên vùng **tác động lớn và khả năng xảy ra thực tế**, thay vì chạy theo 100% coverage trên toàn repository.

### 21.1. Critical-path review

Với mỗi luồng quan trọng:

1. Liệt kê điều kiện đầu vào.
2. Xác định tác dụng phụ bắt buộc.
3. Xác định kết quả/exception/HTTP status đúng.
4. Tìm ranh giới, trạng thái lỗi và phép chuyển trạng thái.
5. Chọn test thuộc cấp độ thích hợp.
6. Kiểm tra coverage có bỏ vùng quan trọng không.
7. Dùng mutation testing để đánh giá sức mạnh assertions tại vùng logic được chọn.

## 22. CI pipeline phù hợp cho coverage và mutation

Mutation testing tiêu tốn tài nguyên hơn test thông thường vì phải chạy nhiều phiên bản mutant. Không cần bắt mọi pull request chạy toàn bộ mutations của mọi module nếu chi phí quá cao.

Một cách bố trí:

~~~mermaid
flowchart LR
    A["Commit / Pull request"]
    B["Compile + lint"]
    C["Unit tests + coverage"]
    D["Integration/contract tests"]
    E["PIT targeted/diff"]
    F["Review survivors quan trọng"]
    G["Merge khi checks đạt"]
    H["Mutation rộng theo lịch"]
    A --> B --> C --> D --> E --> F --> G
    G -.-> H
~~~

### 22.1. Pull request nhanh

- Chạy unit tests, static checks và coverage.
- Chạy integration tests thích hợp với vùng thay đổi.
- Mutation testing ở package/module có rủi ro cao hoặc code vừa thay đổi, nếu hạ tầng hỗ trợ.
- Giữ thời gian phản hồi hợp lý.

### 22.2. Job định kỳ

- Chạy mutation testing rộng hơn, ví dụ theo lịch phù hợp với nhóm.
- Theo dõi xu hướng survivors, no-coverage và thời gian chạy.
- Mở issue/chore cho những chỗ cần xử lý.

### 22.3. Ngưỡng coverage/mutation nên đặt thế nào?

Không có con số 80%, 90% hay 100% đúng cho mọi dự án.

Có thể khởi đầu từ baseline và cam kết:

- Không để coverage của **code mới quan trọng** giảm xuống mà thiếu lý do.
- Không để **critical mutants** còn sống mà không được review.
- Tăng dần chất lượng theo khu vực có rủi ro.
- Có exception/waiver rõ ràng cho generated code hoặc equivalent mutants.
- Không dùng exclude như cách làm đẹp kết quả.

PIT hỗ trợ ngưỡng mutation, coverage và test strength; lưu ý cách làm tròn phần trăm/precision khi cấu hình threshold để tránh những regression nhỏ bị bỏ qua.

## 23. Mutation testing và chi phí chạy

Giả sử test suite có 2.000 tests và engine tạo 5.000 mutants. Chạy cả bộ test từ đầu cho mỗi mutant sẽ rất tốn kém.

Công cụ như PIT tận dụng phân tích coverage và test selection để chạy **những test liên quan**, nhưng chi phí vẫn có thể cao.

### 23.1. Cách giảm chi phí hợp lý

- Tập trung vào code vừa thay đổi hoặc package có rủi ro.
- Giữ unit tests nhanh và độc lập.
- Tránh setup chung cực đắt cho mỗi test.
- Sử dụng lịch phân tích rộng hơn ngoài PR khi phù hợp.
- Cân nhắc incremental/history và caching do công cụ cung cấp.
- Đo tốc độ thực tế trước khi tăng số luồng mutation worker.
- Không để nhiều job tranh CPU/RAM của cùng một build agent tới mức sinh timeout giả.

### 23.2. Không giảm chi phí bằng cách loại bỏ test quan trọng

Nếu bỏ các test tính tiền vì chạy lâu rồi mutation score tăng, số liệu trở nên thiếu ý nghĩa. Hãy sửa tốc độ setup/fixture, chia cấp độ test và quản lý lịch chạy.

## 24. Trường hợp mutation testing dễ gây hiểu nhầm

### 24.1. Mutant sống vì code không thể đạt tới

Một nhánh có thể là phần phòng vệ, đặc điểm unreachable theo một invariant khác, hoặc code chết. Phân tích hợp đồng và loại bỏ code không cần thiết nếu được phép; đừng viết một test trái quy tắc chỉ để chạm nó.

### 24.2. Một assertion fail vì lỗi ngoài mutant

Nếu test fail vì mạng không ổn định hoặc timeout môi trường, PIT có thể báo mutant killed dù bản thân thay đổi sai không phải nguyên nhân. Khi nghi ngờ, chạy lại testcase dưới cùng điều kiện và tìm failure message liên quan.

### 24.3. Mã sinh tự động

Code generated, Lombok, bridge methods, record methods hoặc các bytecode transformations có thể ảnh hưởng report. JaCoCo có bộ lọc cho một số pattern, PIT cũng có các bộ lọc riêng.

Không ngầm loại toàn bộ record hoặc generated code nếu đó là logic nghiệp vụ có tác động thực. Cấu hình filter cần được review và lưu trong version control.

### 24.4. Concurrent logic

Một test có thể kill các mutants toán tử mà vẫn bỏ lọt race condition hiếm. Mutation testing bytecode không thay cho stress tests, structured concurrency tests hoặc công cụ kiểm tra concurrency.

### 24.5. Equivalent mutants

Survivors không phải lúc nào cũng là thiếu test; việc chứng minh equivalent phụ thuộc toàn bộ miền hợp lệ, trạng thái và side effects. Ghi nhận bằng chứng, tránh loại trừ mù quáng.

## 25. Checklist đánh giá một bộ test

- [ ] Các quy tắc nghiệp vụ quan trọng có **expected outputs** độc lập.
- [ ] Có test ngay trước, đúng và sau ranh giới.
- [ ] Có test input không hợp lệ, null/empty nếu hợp đồng yêu cầu.
- [ ] Test không chỉ dựa vào **assertDoesNotThrow** khi cần kiểm tra kết quả.
- [ ] Unit tests không phụ thuộc mạng/DB/đồng hồ ngoài tầm kiểm soát.
- [ ] Các test chạy ổn định khi lặp lại và có thể chạy theo thứ tự khác.
- [ ] Coverage report có thông tin execution thật, không bị skip hoặc sai instrumentation.
- [ ] Line và branch coverage được diễn giải đúng giới hạn.
- [ ] Mutation testing dùng toolchain hỗ trợ Java 27 và test engine tương ứng.
- [ ] SURVIVED/NO_COVERAGE được phân tích riêng.
- [ ] Những equivalent mutants có bằng chứng và ngoại lệ được review.
- [ ] Bộ test quan trọng được đánh giá bằng rủi ro nghiệp vụ, không chỉ score.
- [ ] Integration/security/concurrency/performance được bổ sung khi cần.
- [ ] CI có feedback nhanh, job mutation mở rộng có lịch chạy phù hợp.
- [ ] Test failures chỉ rõ quy tắc nào bị vi phạm.
- [ ] Mọi thay đổi mức ngưỡng và exclude được ghi lại và review.

## 26. Bài thực hành

### Bài A — Từ coverage cao nhưng test yếu

1. Tạo **ShippingPolicy.java** theo mục 3.
2. Chạy nhóm test yếu chỉ dùng **assertDoesNotThrow** và một test ngoại lệ.
3. Ghi JaCoCo line/branch coverage cho method **feeCents**.
4. Chủ động sửa toán tử **>=** thành **>** trong một bản code kiểm thử.
5. Quan sát test yếu có phát hiện sai tại ngưỡng 5.000 không.
6. Thay bằng bộ **ShippingPolicyTest** có expected values cụ thể.
7. Chạy lại và giải thích vì sao coverage có thể ít đổi nhưng chất lượng tăng.

**Không sửa mã production đang dùng chung** để cố làm mutation bằng tay; hãy làm trong một nhánh/thư mục thực hành riêng hoặc dùng PIT trên môi trường kiểm thử.

### Bài B — Mutation testing với PIT

1. Cấu hình PIT phiên bản hỗ trợ Java 27 và JUnit Jupiter đang dùng.
2. Chỉ chọn package **example** và class **ShippingPolicy**.
3. Chạy mutation test và xem mutants của toán tử ranh giới.
4. Liệt kê KILLED, SURVIVED, NO_COVERAGE.
5. Với một survivor, nêu đầu vào làm hai phiên bản khác nhau.
6. Thêm test phù hợp hợp đồng, chạy lại.
7. Nếu nghi equivalent mutant, chứng minh tại sao không có hành vi hợp lệ phân biệt.
8. Ghi thời gian chạy và nhận xét khi nào nên chạy job trong CI.

### Bài C — Đánh giá một module thực tế

Chọn một service có tính giá, kiểm tra quyền hoặc chuyển trạng thái. Lập bảng:

| Quy tắc | Rủi ro khi sai | Test hiện có | Coverage | Mutant survived | Hành động |
|---|---|---|---|---|---|
| Kiểm tra giá trị âm | Chấp nhận dữ liệu sai | ... | ... | ... | ... |
| Ngưỡng miễn phí | Sai phí ranh giới | ... | ... | ... | ... |
| Express surcharge | Thu thiếu/thừa phí | ... | ... | ... | ... |
| Quyền truy cập | Lộ thông tin | ... | ... | ... | ... |

Sau đó đưa ra tối đa ba cải thiện có tác động lớn nhất, kèm chi phí triển khai và cách xác minh.

## 27. Câu hỏi tự đánh giá

1. Vì sao 100% line coverage không có nghĩa test đã kiểm tra kết quả đúng?
2. C0 và C1 trong JaCoCo khác nhau thế nào?
3. Vì sao exception handling không được JaCoCo tính như branch theo định nghĩa C1?
4. Tại sao một dòng Java có thể chứa nhiều khả năng chạy khác nhau?
5. Mutation testing tạo mutant từ đâu với PIT?
6. KILLED khác SURVIVED thế nào?
7. NO_COVERAGE khác SURVIVED ở điểm nào?
8. Một mutant **>= → >** sẽ được phát hiện bởi trường hợp nào?
9. Vì sao một mutant có thể tương đương bản gốc?
10. Test strength và mutation score khác nhau khi có NO_COVERAGE thế nào?
11. Khi nào snapshot test có thể trở thành oracle yếu?
12. Vì sao chạy 1.000 dữ liệu cùng một phân hoạch không bù cho việc thiếu boundary test?
13. Cần kiểm soát những nguồn flakiness nào trước khi chạy PIT?
14. JMH hoặc load test có thay thế mutation testing được không? Vì sao?
15. Vì sao một test tích hợp quan trọng có thể đáng giá dù tăng coverage ít?
16. Làm cách nào để đặt quality gate không khuyến khích gian lận số liệu?
17. Tại sao build cần toolchain JaCoCo hỗ trợ class file Java 27?
18. Nếu mutation score tăng nhưng production bugs không giảm, bạn sẽ điều tra điều gì?

## 28. Ghi nhớ

- **Coverage đo code đã được thực thi**, không trực tiếp đo chất lượng của assertions.
- **JaCoCo** có instruction, branch, line, method, class và complexity counters; C1 tập trung vào **if/switch**, không coi exception handling là branch.
- **Mutation testing** cố ý tạo biến đổi nhỏ để kiểm tra bộ test có phát hiện lỗi giả lập hay không.
- **PIT** tạo mutants trên bytecode; kết quả **KILLED**, **SURVIVED**, **NO_COVERAGE** cần được diễn giải khác nhau.
- **Mutant survived** nên dẫn đến điều tra input/oracle/hợp đồng; không mặc nhiên là equivalent.
- **Mutation score** và **test strength** có thể khác nhau khi tồn tại code chưa được bao phủ.
- **Boundary values** và **test oracle độc lập** thường giúp kill mutants có ý nghĩa hơn việc chỉ gọi thêm method.
- **JaCoCo 0.8.16** chính thức hỗ trợ Java 27; các plugin PIT/JUnit/Gradle/Maven cũng cần được chọn phù hợp.
- Coverage và mutation testing **không thay thế** integration, security, concurrency, performance hay resilience testing.
- Bộ test tốt phải **đúng, ổn định, chẩn đoán được, đủ nhanh và bảo vệ rủi ro nghiệp vụ**.
- Không chạy theo một tỷ lệ phần trăm duy nhất hoặc thêm exclusions để làm đẹp báo cáo.
- Chạy unit+coverage thường xuyên; mutation analysis có thể theo vùng thay đổi hoặc theo lịch để cân bằng chi phí.
- Mục tiêu cuối cùng là **phát hiện regression quan trọng sớm**, chứ không phải đạt điểm số tuyệt đối.

## Tài liệu tham khảo

- [JaCoCo — Coverage Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html)
- [JaCoCo — Change History (Java 27 support)](https://www.jacoco.org/jacoco/trunk/doc/changes.html)
- [JaCoCo — Frequently Asked Questions](https://www.jacoco.org/jacoco/trunk/doc/faq.html)
- [JaCoCo — Gradle Plugin Integration](https://www.jacoco.org/jacoco/trunk/doc/integrations.html)
- [PIT — Basic Concepts](https://pitest.org/quickstart/basic_concepts/)
- [PIT — Mutation Operators](https://pitest.org/quickstart/mutators/)
- [PIT — Maven Quickstart and Quality Thresholds](https://pitest.org/quickstart/maven/)
- [PIT — FAQ](https://pitest.org/faq/)
- [JUnit — User Guide](https://docs.junit.org/current/user-guide/)
- [JUnit — Parameterized Classes and Tests](https://docs.junit.org/current/writing-tests/parameterized-classes-and-tests.html)
- [Gradle — JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html)
- [Java SE 27 — Java Platform API](https://docs.oracle.com/en/java/javase/27/docs/api/)
