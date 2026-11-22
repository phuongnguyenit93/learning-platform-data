# Tính đúng đắn so với yêu cầu và hợp đồng

Một đoạn mã có thể biên dịch thành công, chạy nhanh và được trình bày rất gọn, nhưng vẫn là mã kém chất lượng nếu trả về kết quả sai so với điều người dùng và hệ thống mong đợi. Trong các chiều chất lượng mã nguồn của **CODE_QUALITY_FUNDAMENTALS**, tính đúng đắn (*correctness*) trả lời câu hỏi nền tảng: **Phần mềm có thực hiện đúng hành vi đã được yêu cầu và cam kết hay không?**

Tính đúng đắn cần được đánh giá qua những điều có thể quan sát hoặc kiểm chứng: kết quả đầu ra, thay đổi trạng thái, lỗi được trả về, dữ liệu được lưu, thông điệp được gửi và cách hệ thống xử lý các trường hợp biên. Một hàm cho kết quả đúng ở vài dữ liệu mẫu chưa đủ để kết luận hàm đó đúng với toàn bộ miền dữ liệu mà hợp đồng cho phép.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **yêu cầu**, **hợp đồng** và **mã triển khai** khi đánh giá tính đúng đắn.
2. Xác định tiền điều kiện, hậu điều kiện, bất biến và hành vi lỗi của một chức năng.
3. Chuyển phát biểu nghiệp vụ thành các quy tắc có thể kiểm thử, đặc biệt tại các giá trị biên.
4. Viết và đọc kiểm thử JUnit thể hiện hợp đồng thay vì chỉ lặp lại cách cài đặt.
5. Nhận ra những tình huống mà mã đúng ở cấp hàm nhưng chưa đúng ở cấp hệ thống, chẳng hạn khi có truy cập đồng thời.

## 1. Tính đúng đắn nghĩa là gì?

Một triển khai được xem là đúng **trong một phạm vi đã xác định** nếu hành vi thực tế của nó thỏa mãn những yêu cầu và hợp đồng áp dụng cho phạm vi đó.

Có thể hình dung mối liên hệ:

~~~text
Nhu cầu nghiệp vụ / người dùng
              ↓ làm rõ
Yêu cầu có thể kiểm chứng
              ↓ đặc tả
Hợp đồng (đầu vào, đầu ra, trạng thái, lỗi)
              ↓ triển khai
Mã chương trình
              ↓ kiểm chứng và xác nhận
Bằng chứng: kiểm thử, review, quan sát hệ thống
~~~

Những tầng này liên quan chặt chẽ nhưng không đồng nghĩa:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Yêu cầu** (*requirement*) | Người dùng hay hệ thống cần điều gì? | Người dùng được rút toàn bộ số dư còn lại trong ví. |
| **Hợp đồng** (*contract*) | Với điều kiện nào, thành phần phải bảo đảm điều gì? | Nếu số dư là 500.000 đồng và rút 500.000 đồng, số dư mới phải là 0. |
| **Triển khai** (*implementation*) | Mã hiện thực hóa hợp đồng bằng cách nào? | Kiểm tra số tiền rút rồi tính phép trừ trên kiểu `long`. |
| **Bằng chứng** (*evidence*) | Dựa vào đâu biết mã tuân thủ hợp đồng? | Test cho trường hợp thông thường, rút hết tiền, số tiền không hợp lệ và rút quá số dư. |

Yêu cầu có thể mô tả quy tắc nghiệp vụ hoặc ràng buộc kỹ thuật. Hợp đồng biến các quy tắc đó thành kỳ vọng rõ ràng tại ranh giới của hàm, lớp, API hay dịch vụ. **Kiểm thử xác nhận mã làm đúng hợp đồng; việc rà soát hợp đồng với người có thẩm quyền giúp tránh triển khai rất đúng một đặc tả vốn đã sai yêu cầu.**

### Đúng với đầu vào nào?

Kết luận “hàm này đúng” luôn cần ngữ cảnh. Ví dụ, một hàm tính số tiền chỉ hỗ trợ **số nguyên không âm tính theo đồng Việt Nam** thì không có nghĩa hàm phải xử lý số thực, chuỗi văn bản hoặc các loại tiền khác. Ngược lại, nếu hợp đồng chấp nhận số dư bằng 0, việc từ chối giá trị đó là lỗi dù lập trình viên chỉ thử với số dư dương.

Vì vậy, khi đánh giá correctness, hãy xác định rõ:

- **Miền đầu vào hợp lệ:** kiểu dữ liệu, phạm vi giá trị, đơn vị đo, giới hạn độ dài, định dạng.
- **Kết quả và tác động mong đợi:** giá trị trả về, thay đổi dữ liệu, thứ tự sự kiện, tính nhất quán.
- **Hành vi khi đầu vào không hợp lệ:** từ chối bằng lỗi nào, giữ nguyên trạng thái hay có quy tắc xử lý khác.
- **Điều kiện môi trường:** dữ liệu lưu trữ, thời điểm, múi giờ, phiên bản API, giao dịch hoặc truy cập đồng thời khi chúng ảnh hưởng đến hành vi.

## 2. Hợp đồng phần mềm gồm những gì?

Trong tư duy *Design by Contract*, ba thành phần cốt lõi là **tiền điều kiện**, **hậu điều kiện** và **bất biến**. Khi thiết kế API thực tế, cũng cần mô tả rõ lỗi và những tác dụng phụ có thể quan sát.

### 2.1. Tiền điều kiện (*precondition*)

Là điều kiện phải đúng khi thao tác bắt đầu để thành phần có thể thực hiện cam kết của nó. Ví dụ: số dư hiện tại không âm; số tiền muốn rút phải lớn hơn 0 và không vượt quá số dư.

Tiền điều kiện thể hiện trách nhiệm ở ranh giới gọi hàm. Một API có thể quy định rằng lời gọi sai tiền điều kiện bị từ chối bằng ngoại lệ cụ thể. Không nên mặc định mọi API đều tự xử lý được mọi đầu vào: **cách phản ứng với đầu vào vi phạm phải được đặc tả**.

### 2.2. Hậu điều kiện (*postcondition*)

Là điều phải đúng sau khi thao tác hoàn tất thành công, với giả định tiền điều kiện đã được đáp ứng. Ví dụ: số dư mới bằng số dư ban đầu trừ số tiền rút; kết quả không âm.

Hậu điều kiện cần mô tả điều có thể kiểm chứng, thay vì mô tả thuật toán. “Trả về số dư mới đúng bằng phép trừ” là một cam kết; “dùng câu lệnh if rồi thực hiện phép trừ” chỉ là chi tiết triển khai.

### 2.3. Bất biến (*invariant*)

Là tính chất cần được duy trì tại những thời điểm quan sát trạng thái hợp lệ của đối tượng hoặc hệ thống. Ví dụ: một ví tiền không cho phép thấu chi thì số dư luôn không âm sau mỗi giao dịch đã hoàn tất.

Bất biến khác hậu điều kiện ở chỗ nó áp dụng xuyên suốt nhiều thao tác, chẳng hạn nạp tiền, rút tiền và hoàn tiền. Trong cơ sở dữ liệu, một ràng buộc như **CHECK (balance >= 0)** có thể hỗ trợ duy trì bất biến ở lớp lưu trữ.

### 2.4. Hành vi lỗi và tác dụng phụ

Hợp đồng tốt còn chỉ rõ điều gì xảy ra khi yêu cầu bị từ chối: loại lỗi, mã HTTP hoặc mã lỗi miền nghiệp vụ, thông điệp hữu ích, có lưu hay gửi sự kiện hay không. Chẳng hạn, nếu rút quá số dư, hệ thống phải từ chối và **không làm thay đổi số dư**.

Các khái niệm trên có thể tóm tắt bằng một cam kết có điều kiện:

> Nếu tiền điều kiện đúng khi bắt đầu, thao tác thành công phải thỏa mãn hậu điều kiện và duy trì các bất biến liên quan; nếu thao tác bị từ chối, hệ thống phải tuân thủ hành vi lỗi đã công bố.

## 3. Từ yêu cầu nghiệp vụ đến hợp đồng kiểm chứng được

Xét yêu cầu ban đầu:

> “Người dùng được rút tiền từ ví miễn là còn đủ số dư.”

Câu này chưa đủ để lập trình chính xác. “Đủ số dư” có bao gồm trường hợp rút hết tiền không? Có cho phép rút 0 đồng không? Đơn vị tính là đồng hay nghìn đồng? Nếu rút quá số dư, API trả lỗi gì? Nếu hai yêu cầu đến cùng lúc thì sao?

Sau khi làm rõ với bên quyết định nghiệp vụ, ta có thể đưa ra **hợp đồng minh họa** cho một phép tính rút tiền:

| Mã | Quy tắc đã làm rõ | Cách kiểm chứng |
| --- | --- | --- |
| R1 | Số dư đầu vào là số nguyên không âm, tính bằng VND. | Từ chối số dư âm. |
| R2 | Số tiền rút là số nguyên dương, tính bằng VND. | Từ chối 0 và số âm. |
| R3 | Số tiền rút **không vượt quá** số dư hiện tại. | Chấp nhận khi bằng số dư; từ chối khi lớn hơn. |
| R4 | Với đầu vào hợp lệ, trả về số dư mới = số dư cũ − số tiền rút. | So sánh kết quả với giá trị kỳ vọng. |
| R5 | Đầu vào không hợp lệ gây ra `IllegalArgumentException`. | Kiểm tra loại ngoại lệ. |
| R6 | Phép tính thuần không ghi dữ liệu hoặc phát sự kiện. | Không có tác dụng phụ trong hàm tính toán. |

Đây là **quy ước của ví dụ**, không phải quy định mặc định cho mọi ứng dụng ngân hàng hay ví điện tử. Trong hệ thống thực tế, chính sách lỗi, số tiền tối thiểu, phí, hạn mức, thấu chi và quy tắc đồng thời phải được chốt theo nghiệp vụ.

Viết kịch bản theo định dạng *Given / When / Then* giúp các bên cùng đọc được một cách:

~~~text
Given ví có 500.000 VND
When  người dùng yêu cầu rút 500.000 VND
Then  phép rút được chấp nhận
And   số dư mới bằng 0 VND
~~~

Từ khóa quan trọng là **“không vượt quá”**: tại ranh giới bằng nhau, thao tác hợp lệ. Nếu không làm rõ điểm này, hai lập trình viên có thể chọn hai cách kiểm tra khác nhau.

## 4. Ví dụ Java: một lỗi nhỏ làm sai hợp đồng

Hãy xem triển khai có vẻ hợp lý sau:

~~~java
public static long afterWithdrawal(long balanceVnd, long amountVnd) {
    if (balanceVnd < 0 || amountVnd <= 0 || amountVnd >= balanceVnd) {
        throw new IllegalArgumentException("Invalid withdrawal");
    }
    return balanceVnd - amountVnd;
}
~~~

Hàm này cho kết quả đúng khi rút 200.000 đồng từ số dư 500.000 đồng. Nhưng điều kiện **amountVnd >= balanceVnd** đã vô tình từ chối trường hợp rút đúng toàn bộ số dư. Đó là một lỗi correctness do dùng **>=** thay vì **>**; code vẫn biên dịch và các kiểm thử chỉ dùng dữ liệu thông thường có thể vẫn xanh.

Triển khai bám sát hợp đồng đã nêu:

~~~java
public final class WalletRules {
    private WalletRules() {
        // Utility class: không tạo đối tượng.
    }

    /**
     * Tính số dư sau khi rút tiền, đơn vị VND.
     *
     * @param balanceVnd số dư hiện có, phải >= 0
     * @param amountVnd số tiền rút, phải > 0 và <= balanceVnd
     * @return số dư mới, bằng balanceVnd - amountVnd
     * @throws IllegalArgumentException nếu đầu vào vi phạm hợp đồng
     */
    public static long afterWithdrawal(long balanceVnd, long amountVnd) {
        if (balanceVnd < 0) {
            throw new IllegalArgumentException("Balance must be non-negative");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (amountVnd > balanceVnd) {
            throw new IllegalArgumentException("Insufficient balance");
        }
        return balanceVnd - amountVnd;
    }
}
~~~

Với kiểu **long**, các giá trị đầu vào đã được giới hạn như trên thì phép trừ không thể tràn số: kết quả nằm trong đoạn từ 0 đến số dư đầu vào. Kiểu số nguyên theo **đơn vị tiền nhỏ nhất được quy định** cũng tránh lỗi biểu diễn số thập phân nhị phân thường gặp khi dùng **double** để tính tiền. Nếu nghiệp vụ hỗ trợ tiền tệ có phần lẻ hoặc nhiều loại tiền, cần đặc tả đơn vị, độ chính xác và quy tắc làm tròn; có thể sử dụng **BigDecimal** phù hợp với hợp đồng đó.

### Kiểm thử hợp đồng với JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class WalletRulesTest {

    @Test
    void withdrawsPartOfTheBalance() {
        assertEquals(300_000L, WalletRules.afterWithdrawal(500_000L, 200_000L));
    }

    @Test
    void allowsWithdrawingTheEntireBalance() {
        assertEquals(0L, WalletRules.afterWithdrawal(500_000L, 500_000L));
    }

    @Test
    void rejectsAmountsOutsideTheContract() {
        assertThrows(IllegalArgumentException.class,
                () -> WalletRules.afterWithdrawal(500_000L, 0L));
        assertThrows(IllegalArgumentException.class,
                () -> WalletRules.afterWithdrawal(500_000L, -1L));
        assertThrows(IllegalArgumentException.class,
                () -> WalletRules.afterWithdrawal(500_000L, 500_001L));
    }

    @Test
    void rejectsNegativeStartingBalance() {
        assertThrows(IllegalArgumentException.class,
                () -> WalletRules.afterWithdrawal(-1L, 1L));
    }
}
~~~

Mỗi ca kiểm thử phản ánh một điều trong hợp đồng, không phụ thuộc vào việc hàm được cài bằng bao nhiêu câu lệnh **if**. Nếu sau này đổi cấu trúc mã nhưng giữ nguyên hành vi, bộ kiểm thử vẫn có giá trị. Ngược lại, nếu yêu cầu nghiệp vụ thay đổi, cần cập nhật **hợp đồng và kiểm thử** trước hoặc cùng lúc với triển khai.

### Các trường hợp nên thử thêm

| Đầu vào (số dư, tiền rút) | Kỳ vọng | Lý do |
| --- | --- | --- |
| (500.000, 200.000) | 300.000 | Luồng thông thường. |
| (500.000, 500.000) | 0 | Ranh giới bằng số dư, phải chấp nhận. |
| (500.000, 500.001) | Ngoại lệ | Vừa vượt ranh giới. |
| (500.000, 1) | 499.999 | Số tiền dương nhỏ nhất theo đơn vị đã chọn. |
| (0, 1) | Ngoại lệ | Ví trống không thể rút số tiền dương. |
| (500.000, 0) | Ngoại lệ | Vi phạm tiền điều kiện số tiền rút dương. |
| (-1, 1) | Ngoại lệ | Trạng thái đầu vào không hợp lệ. |
| (Long.MAX_VALUE, Long.MAX_VALUE) | 0 | Trường hợp lớn nhất hợp lệ của kiểu dữ liệu. |

Ngoài ví dụ cụ thể, có thể kiểm tra **tính chất tổng quát**: với mọi số dư hợp lệ **b** và số tiền **a** thỏa mãn **0 < a <= b**, kết quả **r** phải thỏa **r >= 0** và **r + a = b**. Kiểm thử dựa trên tính chất (*property-based testing*) có thể sinh nhiều bộ dữ liệu trong miền này; tuy vậy, nó vẫn phụ thuộc vào việc ta đã xác định đúng tính chất cần bảo đảm.

## 5. Đúng ở cấp hàm chưa chắc đúng ở cấp hệ thống

Hàm **afterWithdrawal** là một phép tính thuần: nhận hai số rồi trả về một số. Trong một dịch vụ ví điện tử thực, số dư được lưu trong cơ sở dữ liệu và nhiều yêu cầu có thể đến cùng lúc.

Giả sử ví có 100.000 đồng. Hai yêu cầu rút 80.000 đồng cùng đọc số dư 100.000, cùng tính ra 20.000 và cùng chấp nhận giao dịch. **Từng phép tính riêng lẻ tuân thủ hợp đồng đầu vào**, nhưng tổng số tiền được chấp nhận rút là 160.000 đồng. Kết quả toàn hệ thống vi phạm bất biến “không được chi vượt số dư”.

Để đáp ứng hợp đồng ở cấp hệ thống, cần thiết kế cập nhật số dư một cách nguyên tử, chẳng hạn dùng một câu lệnh cập nhật có điều kiện trong giao dịch:

~~~sql
UPDATE wallet
SET balance = balance - :amount
WHERE id = :wallet_id
  AND balance >= :amount;
~~~

Ứng dụng phải kiểm tra trước rằng **amount > 0**, kiểm tra số dòng được cập nhật, xử lý trường hợp ví không tồn tại và tuân theo chiến lược giao dịch của hệ thống. Cách tiếp cận này chỉ là **một phần** của giải pháp: việc ghi nhận lịch sử, chuyển tiền ra hệ thống bên ngoài, retry và chống xử lý trùng lặp còn cần hợp đồng riêng.

Ví dụ cho thấy “đúng” không chỉ là kết quả một biểu thức toán học. **Phạm vi hợp đồng đến đâu thì phạm vi chứng minh và kiểm thử phải mở rộng đến đó**: hàm, lớp, dịch vụ, cơ sở dữ liệu hay toàn bộ luồng nghiệp vụ.

## 6. Những cách phát hiện và ngăn ngừa sai lệch

Tính đúng đắn nên được chăm sóc từ lúc hiểu yêu cầu cho tới lúc vận hành. Các kỹ thuật dưới đây cung cấp những loại bằng chứng khác nhau:

| Hoạt động | Phát hiện được điều gì? | Hạn chế cần nhớ |
| --- | --- | --- |
| Rà soát yêu cầu và ví dụ chấp nhận | Thuật ngữ mơ hồ, điều kiện thiếu, hiểu sai ngưỡng. | Cần xác nhận từ người sở hữu nghiệp vụ. |
| Review thiết kế và code | Nhánh logic sai, thiếu kiểm tra, giả định không được ghi rõ. | Người review có thể cùng chia sẻ một hiểu lầm. |
| Kiểm thử đơn vị | Hàm/lớp vi phạm hợp đồng ở các ca đã chọn. | Không bao trùm tất cả trạng thái và tương tác. |
| Kiểm thử tích hợp / hợp đồng API | Sai khác giữa các thành phần, kiểu dữ liệu, mã lỗi, dữ liệu lưu. | Không thay thế kiểm thử luồng nghiệp vụ đầy đủ. |
| Kiểm thử theo tính chất và trường hợp biên | Sai lệch trên nhiều tổ hợp dữ liệu, quy luật bất biến. | Chất lượng phụ thuộc vào thuộc tính được nêu. |
| Phân tích tĩnh, kiểu dữ liệu, ràng buộc DB | Một số lỗi tiềm ẩn, vi phạm kiểu, trạng thái dữ liệu sai. | Không tự xác định được toàn bộ mục đích nghiệp vụ. |
| Quan sát sản phẩm khi vận hành | Sai lệch chỉ xuất hiện với dữ liệu và tương tác thực tế. | Phát hiện sau triển khai, không chứng minh hết lỗi. |

Một thói quen hiệu quả là lập **ma trận truy vết** đơn giản: mỗi yêu cầu có ít nhất một cách kiểm chứng. Ví dụ R3 “cho phép rút đúng bằng số dư” có kiểm thử **allowsWithdrawingTheEntireBalance**; R5 “đầu vào sai gây ngoại lệ” được gắn với các kiểm thử từ chối đầu vào.

**Độ bao phủ mã (code coverage) cao không đồng nghĩa tính đúng đắn cao.** Một bộ test chạy qua mọi nhánh nhưng mong đợi sai kết quả theo yêu cầu vẫn có thể đạt coverage 100%. Cũng vậy, mã sạch và dễ đọc giúp người khác phát hiện lỗi nhưng không tự bảo đảm hành vi đúng.

### Kiểm tra cả đường đi bất thường

Trong hệ thống có trạng thái hoặc tích hợp bên ngoài, cần hỏi thêm:

- Nếu dữ liệu không tồn tại, hệ thống trả về điều gì?
- Nếu thao tác thất bại giữa chừng, có để lại trạng thái dở dang không?
- Nếu yêu cầu được gửi lại, kết quả có bị nhân đôi không?
- Nếu hai người thao tác đồng thời, bất biến còn được giữ không?
- Nếu thời gian, làm tròn, múi giờ hoặc thứ tự sự kiện ảnh hưởng kết quả, quy tắc nào là chuẩn?

Chỉ kiểm thử luồng thành công (*happy path*) thường bỏ lỡ chính các sai lệch này.

## 7. Phân biệt tính đúng đắn với các chiều chất lượng khác

| Chiều chất lượng | Câu hỏi trọng tâm | Quan hệ với correctness |
| --- | --- | --- |
| **Tính đúng đắn** | Hành vi có thỏa yêu cầu và hợp đồng không? | Trọng tâm của bài này. |
| **Tính dễ đọc, dễ bảo trì** | Có dễ hiểu, sửa đổi và kiểm tra mã không? | Giúp duy trì tính đúng đắn khi thay đổi, nhưng không thay thế nó. |
| **Độ tin cậy** (*reliability*) | Hệ thống có tiếp tục đáp ứng kỳ vọng trong thời gian và điều kiện vận hành không? | Có liên hệ chặt với đúng đắn, nhưng nhấn mạnh sự ổn định khi vận hành. |
| **Khả năng chống chịu lỗi** (*robustness*) | Hệ thống xử lý điều kiện bất thường và lỗi ngoài dự kiến như thế nào? | Bổ sung vào hợp đồng nếu có yêu cầu rõ về hành vi khi lỗi. |
| **Hiệu năng** (*performance*) | Có đáp ứng yêu cầu về thời gian, tài nguyên, thông lượng không? | Khi giới hạn hiệu năng là yêu cầu bắt buộc, vượt giới hạn cũng là không đạt yêu cầu. |

Ví dụ, chức năng tính hóa đơn ra số tiền chính xác nhưng mất 30 giây vẫn **đúng về giá trị tính toán**, song có thể **không đạt hợp đồng dịch vụ** nếu thời gian phản hồi tối đa được cam kết là 2 giây. Luôn nói rõ đang đánh giá hợp đồng ở cấp nào.

## 8. Các lỗi tư duy thường gặp

**“Code chạy được nên đúng.”** Trình biên dịch chủ yếu kiểm tra cú pháp và kiểu; nó không biết doanh nghiệp có cho rút hết số dư hay không.

**“Có test là đủ.”** Test có thể mã hóa cùng hiểu lầm của người viết code. Hãy đối chiếu kỳ vọng của test với yêu cầu đã được xác nhận.

**“Trường hợp thông thường đúng thì trường hợp biên cũng đúng.”** Lỗi dùng toán tử **>=** thay cho **>** thường chỉ lộ ra ở đúng ranh giới.

**“Hàm thuần đúng thì nghiệp vụ sẽ đúng.”** Cơ sở dữ liệu, quyền truy cập, tính nguyên tử, giao dịch, retry và các hệ thống liên quan có thể làm sai kết quả tổng thể.

**“Không có lỗi trong log nghĩa là không có lỗi.”** Hệ thống có thể trả về kết quả sai một cách im lặng. Cần có kiểm thử và chỉ số đối soát bám sát bất biến nghiệp vụ.

## 9. Quy trình thực hành khi phát triển một chức năng

1. **Đọc và xác nhận mục tiêu:** ai sử dụng, kết quả mong muốn là gì, trường hợp nào bị từ chối.
2. **Làm rõ các khoảng trống:** đơn vị dữ liệu, ngưỡng bao gồm hay loại trừ, giá trị rỗng, trạng thái lỗi, đồng thời, thời gian và làm tròn.
3. **Viết hợp đồng có thể kiểm chứng:** tiền điều kiện, hậu điều kiện, bất biến, lỗi và tác dụng phụ.
4. **Chọn các ca đại diện và biên:** giá trị nhỏ nhất, đúng ngưỡng, vừa vượt ngưỡng, dữ liệu sai và tương tác nhiều thành phần.
5. **Triển khai theo hợp đồng:** dùng kiểu dữ liệu và cơ chế bảo vệ bất biến phù hợp; tránh để quy tắc nghiệp vụ chỉ tồn tại trong giả định của người viết.
6. **Kiểm chứng ở các mức cần thiết:** unit test, integration test, review và quan sát vận hành; liên kết mỗi kiểm chứng với một yêu cầu.
7. **Khi yêu cầu đổi, cập nhật cùng nhau:** yêu cầu → hợp đồng → kiểm thử → triển khai → tài liệu/API liên quan.

### Tự kiểm tra

**Câu 1.** Một hàm hoàn toàn khớp với đặc tả kỹ thuật, nhưng đặc tả ghi “rút số tiền nhỏ hơn số dư” trong khi nghiệp vụ cho phép rút hết. Hàm có đúng không?

*Gợi ý trả lời:* Hàm đúng với đặc tả kỹ thuật đang có nhưng **chưa đúng với yêu cầu nghiệp vụ**. Cần sửa và thống nhất lại đặc tả/hợp đồng, sau đó cập nhật test và mã.

**Câu 2.** Một phương thức cho phép số tiền rút bằng số dư, nhưng không chống hai giao dịch đồng thời cùng sử dụng số dư cũ. Lỗi thuộc phạm vi nào?

*Gợi ý trả lời:* Đây là sai lệch **tính đúng đắn ở cấp hệ thống/trạng thái đồng thời**. Kiểm thử đơn vị của phép tính thuần không đủ để phát hiện; cần kiểm thử tích hợp và cơ chế cập nhật nguyên tử phù hợp.

**Câu 3.** Kiểm thử của hàm rút tiền đạt 100% branch coverage. Có thể kết luận không còn lỗi correctness không?

*Gợi ý trả lời:* Không. Coverage không chứng minh các kỳ vọng đã phản ánh đúng yêu cầu, cũng không bảo đảm mọi dữ liệu, trạng thái và tương tác đều được kiểm tra.

## Ghi nhớ

- **Yêu cầu** xác định điều cần đạt; **hợp đồng** làm rõ các điều kiện và cam kết có thể kiểm chứng; **triển khai** phải tuân theo các cam kết đó.
- Một hợp đồng hữu ích bao gồm **tiền điều kiện, hậu điều kiện, bất biến, hành vi lỗi và tác dụng phụ** khi cần thiết.
- Trường hợp **biên, đầu vào bất hợp lệ và tương tác đồng thời** thường là nơi những sai lệch quan trọng xuất hiện.
- Kiểm thử mang lại bằng chứng, nhưng cần bám theo yêu cầu thực sự và được bổ sung bằng review, kiểm thử tích hợp, ràng buộc dữ liệu và quan sát khi vận hành.

**Nguyên tắc thực hành:** Trước khi hỏi “Đoạn code này hoạt động thế nào?”, hãy hỏi “Với đầu vào và trạng thái nào, hệ thống bắt buộc phải làm gì, và ta kiểm chứng cam kết đó bằng cách nào?”.
