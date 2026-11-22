# Ước lượng có khoảng không chắc chắn thay vì điểm số giả chính xác

Trong buổi lập kế hoạch, nhóm phát triển phát hiện một lớp xử lý đơn hàng đã tích lũy nhiều nhánh đặc biệt. Mỗi lần thêm chính sách khuyến mãi, nhóm phải sửa nhiều nơi và chạy lại nhiều kiểm thử thủ công. Một người đề xuất “trả nợ kỹ thuật trong 12 ngày”, người khác chấm “mức nợ 8,7/10”, rồi bản kế hoạch ghi đúng **12 ngày** như thể đã biết chắc khối lượng công việc.

Nhưng chưa ai xác nhận số test cần bổ sung, ràng buộc database liên quan, hệ thống bên ngoài phụ thuộc hoặc mức độ thay đổi của yêu cầu sắp tới. Con số chính xác đến một chữ số thập phân không làm cho thông tin ban đầu chắc chắn hơn. Ngược lại, nó có thể che khuất các giả định đang chi phối quyết định.

**Ước lượng tốt không giả vờ loại bỏ sự không chắc chắn.** Nó nêu rõ phạm vi công việc, một **khoảng kết quả có cơ sở**, các giả định và cách thu thập bằng chứng để thu hẹp khoảng đó. Nhờ vậy, người ra quyết định biết khi nào nên xử lý nợ ngay, khi nào cần điều tra thêm và khi nào có thể trì hoãn có chủ đích.

Bài học thuộc chương **Nợ kỹ thuật** của module `CODE_QUALITY_FUNDAMENTALS`, nơi chất lượng mã được nhìn qua khả năng **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ước lượng nợ kỹ thuật cần xét cả chi phí sửa cấu trúc, chi phí tiếp tục sống với cấu trúc hiện tại, và rủi ro khi sửa sai. Đây là một quyết định kỹ thuật–sản phẩm, không chỉ là phép cộng số dòng mã.

Sau bài học, bạn có thể:

- Nhận diện **độ chính xác giả** trong điểm nợ, dự báo ngày công hoặc chỉ số tự chế.
- Tách **quan sát**, **giả định** và **bất định** khi lập ước lượng.
- Biểu diễn công sức bằng khoảng giá trị có đơn vị và phạm vi rõ ràng.
- Phân biệt khoảng kịch bản thấp–cao với khoảng xác suất như P50/P90.
- Ước lượng chi phí trả nợ và “lãi nợ” từ những thay đổi thực tế.
- Sử dụng một ví dụ Java nhỏ để tính, kiểm tra và công khai phép cộng khoảng.
- Lựa chọn bước khảo sát, thử nghiệm hoặc refactor nhỏ giúp giảm bất định trước khi cam kết.
- Cập nhật dự báo khi xuất hiện bằng chứng mới, thay vì bám vào con số cũ.

## 1. Nợ kỹ thuật không phải một khoản tiền có sẵn trên sổ sách

Trong phát triển phần mềm, **nợ kỹ thuật** là cách mô tả những lựa chọn hoặc tình trạng kỹ thuật khiến việc thay đổi, vận hành hoặc bảo đảm chất lượng trong tương lai trở nên tốn kém hơn so với một phương án phù hợp hơn. Ví dụ:

- Một bộ quy tắc giá bị sao chép ở ba dịch vụ.
- Logic phân quyền phụ thuộc các cờ và chuỗi khó hiểu.
- Một thư viện quá cũ khiến việc cập nhật bảo mật khó khăn.
- Một repository không có test ở các trạng thái lỗi quan trọng.
- Một mô hình dữ liệu cần chuyển đổi thủ công mỗi khi thêm loại đơn hàng.

**Nợ kỹ thuật không đồng nghĩa với mọi mã cũ, mã dài hoặc bug.** Mã cũ nhưng dễ bảo trì có thể không tạo chi phí đáng kể. Một lỗi sản xuất cần sửa ngay có thể là công việc khắc phục sự cố, còn cải thiện cấu trúc để tránh tái diễn có thể là phần trả nợ. Cần diễn đạt ranh giới rõ thay vì gom mọi việc không thích vào một backlog “technical debt”.

Phép ẩn dụ tài chính thường tách hai phần:

- **“Gốc nợ” (principal) theo nghĩa ẩn dụ:** công sức cần bỏ ra để đưa thiết kế đến trạng thái mục tiêu.
- **“Lãi nợ” (interest) theo nghĩa ẩn dụ:** phần công sức hoặc rủi ro tăng thêm khi tiếp tục làm việc với thiết kế hiện tại.

Không phải mọi nợ đều tích lãi đều đặn như khoản vay. Nếu một vùng mã không thay đổi trong nhiều năm và không gây sự cố, chi phí duy trì có thể thấp. Nếu tháng tới cần mở rộng hệ thống ở chính vùng đó, chi phí có thể tăng đột ngột.

Vì vậy, không có quy tắc đáng tin nào cho phép chuyển trực tiếp “điểm complexity 20” thành “còn nợ 20 ngày công”. Hai đại lượng mô tả những điều khác nhau.

## 2. Độ chính xác giả xuất hiện như thế nào?

**Độ chính xác giả (*false precision*)** xảy ra khi cách trình bày tạo ấn tượng chắc chắn hơn mức bằng chứng thực tế cho phép.

Các ví dụ thường gặp:

```text
"Khoản nợ này mất đúng 12 ngày."

"Chỉ số nợ kỹ thuật = 8,73."

"Refactor làm tăng năng suất nhóm chính xác 27,4%."

"Tỷ lệ hoàn vốn là 143% trong quý sau."
```

Các phát biểu này có thể hợp lý **nếu** phương pháp đo và dữ liệu đủ mạnh, nhưng thường không hợp lý khi mới khảo sát một vài file. Đặc biệt, số chữ số sau dấu thập phân không phản ánh độ tin cậy.

Một cách trình bày hữu ích hơn:

```text
"Nếu phạm vi chỉ gồm module checkout, chúng tôi ước lượng
khoảng 11–31 ngày công phát triển. Khoảng rộng chủ yếu do
chưa rõ ràng buộc tích hợp và khối lượng kiểm thử hồi quy.

Chưa đủ bằng chứng để khẳng định thời hạn hoàn thành.
Cần một thử nghiệm 1–2 ngày nhằm xác định các tích hợp
và chốt phạm vi trước khi lên lịch."
```

Ở đây, **11–31** là một *khoảng kịch bản có điều kiện*, chưa phải khoảng xác suất. Chúng ta không tuyên bố “90% chắc chắn hoàn thành trong khoảng đó” khi chưa có dữ liệu xác suất.

### Câu hỏi nên đặt khi nghe một con số rất cụ thể

1. **Đơn vị là gì?** Ngày công cá nhân, ngày làm việc trên lịch, giờ máy, chi phí hạ tầng hay điểm thứ tự ưu tiên?
2. **Phạm vi gồm gì?** Chỉ sửa code hay gồm test, migration, deployment, giám sát và rollback?
3. **Đến từ đâu?** Kết quả đã đo, lịch sử thay đổi tương tự hay phỏng đoán từ một người?
4. **Điều kiện nào được giả định?** Phụ thuộc ổn định, test hiện có chạy được, không đổi schema?
5. **Nếu giả định sai, kết quả thay đổi bao nhiêu?**
6. **Có bằng chứng để gán xác suất không, hay chỉ có ba kịch bản?**

Đặt những câu hỏi này không có nghĩa là từ chối lập kế hoạch. Mục tiêu là đưa ra cam kết **có điều kiện minh bạch**, thay vì một số duy nhất dễ bị hiểu nhầm thành lời hứa tuyệt đối.

## 3. Phân biệt ba lớp thông tin trong ước lượng

Một bản ước lượng tốt nên phân loại ít nhất ba thứ.

| Loại | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| **Quan sát** | Trong 6 PR gần đây, thay đổi quy tắc giá thường đòi sửa ba file và chạy test hồi quy | Là bằng chứng lịch sử, có nguồn và thời điểm |
| **Giả định** | Quý sau sẽ có 4–8 thay đổi ở chính sách giá | Cần ghi rõ người xác nhận và khả năng đổi |
| **Bất định** | Chưa biết có bao nhiêu consumer dùng API cũ | Cần điều tra; làm rộng khoảng ước lượng |

Một lỗi phổ biến là viết “dự kiến 6 thay đổi” rồi chuyển thẳng thành “6 × 2 = 12 ngày tiết kiệm” mà không cho biết **6** là từ roadmap đã xác nhận, thống kê hay suy đoán.

Tương tự, ước lượng công sức 10 ngày từ một nhiệm vụ cũ chưa chắc áp dụng được nếu dự án mới thiếu test, có yêu cầu tương thích ngược hoặc đang phải giữ hai phiên bản API song song.

### Bất định do thiếu hiểu biết và biến động tự nhiên

Hai nguồn bất định hữu ích cần phân biệt:

- **Bất định do thiếu hiểu biết (*epistemic uncertainty*):** chưa biết consumer nào dùng API, chưa biết phạm vi SQL, chưa thử migration. Có thể giảm bằng khảo sát, spike, prototype hoặc kiểm thử.
- **Biến động vốn có (*aleatory variability*):** thời gian review, tải sản xuất, số lần thay đổi yêu cầu hoặc sự cố tương lai có thể biến động dù đã hiểu hệ thống khá rõ.

Một cuộc khảo sát dependency có thể thu hẹp khoảng công sức do thiếu hiểu biết, nhưng không thể bảo đảm quý sau có đúng sáu yêu cầu tính năng. Hai loại bất định cần được xử lý bằng phương pháp phù hợp.

## 4. Định nghĩa phạm vi trước khi đưa ra khoảng

Giả sử tình huống là lớp `CheckoutManager` tập trung tính giá, lưu đơn, gửi email và nhiều nhánh ngoại lệ. Nhóm muốn tách chính sách giá khỏi luồng checkout để thay đổi khuyến mãi an toàn hơn.

Trước khi ước lượng, cần trả lời:

- Chỉ tách chính sách giá cho **đơn hàng mới**, hay cả hoàn tiền và điều chỉnh đơn cũ?
- Giữ nguyên API và database schema, hay sẽ thay?
- Có bao nhiêu nơi gọi logic giá?
- Cần đối chiếu cách làm tròn, đơn vị tiền, điều kiện biên nào?
- Test hiện có đã đủ làm “lưới an toàn” chưa?
- Có phải phối hợp nhiều nhóm và triển khai theo giai đoạn không?
- Có cần giữ hai cách tính cùng hoạt động trong quá trình chuyển đổi không?

Nếu chưa chốt, “refactor checkout” không phải một đơn vị công việc đủ rõ để đưa ra con số có ý nghĩa.

### Phạm vi gồm cả việc giảm rủi ro

Một dự báo chỉ tính thời gian viết code thường bỏ sót phần tốn nhiều công:

```text
Khảo sát nơi sử dụng
       |
       v
Ghi lại hành vi cũ và các giá trị biên
       |
       v
Tạo hoặc sửa test
       |
       v
Refactor và cập nhật điểm gọi
       |
       v
Kiểm thử tích hợp / dữ liệu thực
       |
       v
Triển khai, quan sát và khả năng rollback
```

Đối với mã liên quan thanh toán hoặc trạng thái dùng chung, bỏ qua các bước kiểm tra để rút ngắn ước lượng có thể làm tăng rủi ro lớn hơn phần công sức tiết kiệm được.

## 5. Dùng khoảng thay vì một điểm duy nhất

Một phương án đơn giản là ghi **khoảng công sức thấp–cao có điều kiện**, cùng lý do:

| Hạng mục cho ví dụ checkout | Thấp (ngày công) | Cao (ngày công) | Nguồn bất định chính |
| --- | ---: | ---: | --- |
| Xây test và tách logic giá | 6 | 10 | Số trường hợp biên chưa có test |
| Điều chỉnh tích hợp và điểm gọi | 3 | 7 | Phạm vi consumer chưa rõ |
| Migration, triển khai và xác minh | 2 | 6 | Mức tương thích và rollback |
| Công sửa phát sinh có điều kiện | 0 | 8 | Phát hiện phụ thuộc hoặc giả định sai |
| **Tổng khoảng minh họa** | **11** | **31** | Phụ thuộc vào phạm vi nêu trên |

Mỗi con số ở bảng là **giả định cho mục đích học tập**, không phải dữ liệu khảo sát một dự án thật. Khi lập ước lượng thực, cần người phụ trách, bằng chứng và các điểm chưa biết cụ thể cho từng hàng.

Với các khoảng không âm trên, cộng cận thấp và cận cao cho khoảng tổng:

\[
[6,10]+[3,7]+[2,6]+[0,8]=[11,31].
\]

Phép cộng khoảng này cho một **bao ngoài có điều kiện** khi từng hạng mục thực sự nằm trong cận đã cho. Nó **không đòi các hạng mục độc lập** để tạo bao ngoài; nhưng không tạo ra xác suất rằng tổng sẽ xuất hiện ở đâu bên trong khoảng.

Cần phân biệt **giới hạn kịch bản** với **giới hạn chắc chắn**. Nếu cận “cao” chỉ là điều nhóm tưởng tượng lúc khảo sát sơ bộ, những rủi ro chưa biết vẫn có thể khiến công việc vượt 31 ngày. Không nên gọi đó là “tối đa chắc chắn”.

### Khoảng rộng không có nghĩa người ước lượng yếu

Khoảng 11–31 phản ánh có nhiều điều chưa rõ. Viết “21 ngày” bằng cách lấy trung điểm \((11+31)/2\) không làm các phụ thuộc biến mất. Nếu người nhận yêu cầu một số duy nhất để đặt lịch, nên cung cấp thêm **mốc cập nhật và điều kiện cam kết**, chứ không xóa phần bất định khỏi báo cáo.

Ví dụ: “Sau spike xác nhận các consumer API và phạm vi test, nhóm sẽ cập nhật khoảng và kế hoạch rollout; hiện chưa chốt ngày hoàn thành.”

## 6. Đừng trộn khoảng kịch bản với khoảng xác suất

Có ít nhất ba cách thường bị gọi chung là “khoảng ước lượng”:

| Cách diễn đạt | Có nghĩa gì? | Được phép suy ra điều gì? |
| --- | --- | --- |
| **Thấp–cao theo kịch bản** | Các mức công sức cho những giả định ít/nhiều việc | Cho thấy độ nhạy với giả định; **không tự chứa xác suất** |
| **Khoảng dự báo được hiệu chỉnh** | Được xây từ phân phối/lịch sử và quy trình dự báo có xác suất | Có thể diễn giải xác suất nếu phương pháp đủ phù hợp |
| **Biên cam kết** | Giới hạn nguồn lực hoặc thời gian được quản lý chấp nhận | Là quyết định quản trị; không đồng nghĩa xác suất thành công |

Nếu một nhóm có dữ liệu tốt về các công việc tương tự và xây mô hình dự báo, họ có thể công bố:

- **P50** của thời gian hoàn thành: theo mô hình, khoảng 50% kết quả không vượt mức này.
- **P90** của thời gian hoàn thành: theo mô hình, khoảng 90% kết quả không vượt mức này.

Đây là các **phân vị của phân phối dự báo**, không phải cách đặt tên cho “ước lượng vừa” và “ước lượng xấu nhất”. Nói “P90 là 25 ngày” đòi hỏi mô hình, dữ liệu và cách kiểm tra hiệu chỉnh; không thể suy ra chỉ từ ba con số lạc quan–thường gặp–bi quan.

Nếu chưa có cơ sở xác suất, hãy dùng từ **kịch bản thấp/trung tâm/cao** và ghi rõ định nghĩa từng mức. Tránh gắn nhãn “90% chắc chắn” cho khoảng ước chừng từ cảm giác.

### Ba mức không tự tạo ra một phân phối

Một nhóm có thể ghi:

```text
Kịch bản thuận lợi: 11 ngày công.
Kịch bản đang xem là hợp lý: 18–22 ngày công.
Kịch bản nhiều trở ngại: khoảng 31 ngày công.
```

Đây là cách trình bày giúp thảo luận, **không** có nghĩa 18–22 là khoảng tin cậy thống kê hoặc 31 là P90. Những nhãn xác suất chỉ nên được thêm khi có phương pháp dự báo đáp ứng ý nghĩa đó.

## 7. Ví dụ Java: biểu diễn khoảng công sức mà không che nguồn gốc

Một kiểu dữ liệu nhỏ giúp tránh lẫn đơn vị và lỗi cộng khoảng:

```java
record EffortRange(int minPersonDays, int maxPersonDays) {
    EffortRange {
        if (minPersonDays < 0 || maxPersonDays < minPersonDays) {
            throw new IllegalArgumentException("Invalid effort range");
        }
    }

    EffortRange plus(EffortRange other) {
        if (other == null) {
            throw new IllegalArgumentException("Range is required");
        }
        return new EffortRange(
                Math.addExact(minPersonDays, other.minPersonDays()),
                Math.addExact(maxPersonDays, other.maxPersonDays())
        );
    }

    EffortRange times(CountRange count) {
        if (count == null) {
            throw new IllegalArgumentException("Count range is required");
        }
        return new EffortRange(
                Math.multiplyExact(
                        minPersonDays, count.minCount()),
                Math.multiplyExact(
                        maxPersonDays, count.maxCount())
        );
    }
}

record CountRange(int minCount, int maxCount) {
    CountRange {
        if (minCount < 0 || maxCount < minCount) {
            throw new IllegalArgumentException("Invalid count range");
        }
    }
}
```

Đoạn mã minh họa Java 17. `EffortRange` biểu diễn **ngày công của một hạng mục**, còn `CountRange` biểu diễn **số lần thay đổi hoặc số công việc**, đều dùng số nguyên không âm để đơn giản hóa. Phương thức `times` chỉ cho phép nhân khoảng ngày công với khoảng số lượng; kiểu khác nhau giúp tránh phép nhân vô nghĩa giữa hai khoảng ngày công. Đây là **phép toán khoảng**, không phải dự báo xác suất.

Sử dụng:

```java
EffortRange logicAndTests = new EffortRange(6, 10);
EffortRange integrations = new EffortRange(3, 7);
EffortRange rollout = new EffortRange(2, 6);
EffortRange unexpectedRework = new EffortRange(0, 8);

EffortRange total = logicAndTests
        .plus(integrations)
        .plus(rollout)
        .plus(unexpectedRework);

System.out.println(total); // EffortRange[minPersonDays=11, maxPersonDays=31]
```

Phép toán làm rõ cách ra con số nhưng **không xác minh các cận đầu vào**. Nếu chưa biết số consumer, `new EffortRange(3, 7)` vẫn chỉ là giả định. Kiểu dữ liệu bảo vệ lỗi biểu diễn; bằng chứng kỹ thuật và thảo luận phạm vi mới bảo vệ chất lượng ước lượng.

### Ngày công khác ngày trên lịch

**Ngày công (*person-day*)** là đơn vị nỗ lực lao động, không tự động bằng một ngày hoàn tất trên lịch. Một việc 20 ngày công có thể cần lâu hơn 20 ngày lịch do review, chờ hệ thống, phụ thuộc nhóm khác hoặc công việc song song không thể chia đều.

Nhân ngày công với số người để suy ngay thời hạn cũng có thể sai: tăng số người chưa chắc giảm thời gian tuyến tính, nhất là khi tri thức, phối hợp và ranh giới thay đổi còn chồng chéo.

Vì vậy, công sức **11–31 ngày công** không được ghi thành “giao trong 11–31 ngày làm việc” nếu chưa lập lịch phụ thuộc và năng lực thực tế của nhóm.

## 8. Kiểm thử phép tính không phải kiểm thử độ đúng của dự báo

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class EffortRangeTest {
    @Test
    void sumsRangesUsingBothBounds() {
        EffortRange result = new EffortRange(6, 10)
                .plus(new EffortRange(3, 7))
                .plus(new EffortRange(2, 6))
                .plus(new EffortRange(0, 8));

        assertEquals(new EffortRange(11, 31), result);
    }

    @Test
    void rejectsInvertedAndNegativeRanges() {
        assertThrows(IllegalArgumentException.class,
                () -> new EffortRange(8, 5));
        assertThrows(IllegalArgumentException.class,
                () -> new EffortRange(-1, 5));
    }

    @Test
    void multipliesNonNegativeBounds() {
        EffortRange extraDaysPerChange = new EffortRange(1, 3);
        CountRange numberOfChanges = new CountRange(4, 8);

        assertEquals(new EffortRange(4, 24),
                extraDaysPerChange.times(numberOfChanges));
    }

    @Test
    void detectsIntegerOverflow() {
        assertThrows(ArithmeticException.class,
                () -> new EffortRange(Integer.MAX_VALUE, Integer.MAX_VALUE)
                        .plus(new EffortRange(1, 1)));
    }
}
```

Những test này xác nhận phép toán và bất biến của kiểu Java, **không chứng minh** refactor thật sẽ tốn 11–31 ngày. Đây là phân biệt quan trọng: một bảng tính có công thức đúng vẫn có thể chứa giả định sai.

Một hệ thống ước lượng chuyên nghiệp có thể dùng cấu trúc số thập phân, phân phối dự báo, mối tương quan và dữ liệu lịch sử. Ví dụ trên chỉ dạy cách **giữ cận và đơn vị rõ ràng** thay vì nén tất cả thành một số rồi quên nguồn.

## 9. Ước lượng “lãi nợ”: công sức tăng thêm khi tiếp tục giữ thiết kế cũ

Một khoản nợ cần được đánh giá so với phương án **chưa trả nợ**, không chỉ dựa trên công sức refactor.

Giả sử các pull request gần đây cho thấy mỗi thay đổi ở chính sách giá đòi khoảng **1–3 ngày công tăng thêm** để sửa logic lặp, điều chỉnh test và kiểm tra hồi quy so với một luồng được tổ chức tốt hơn. Nhóm dự báo có **4–8 thay đổi tương tự** trong quý tới.

Khoảng chi phí tăng thêm **tiềm năng** nếu các điều kiện giống lịch sử được lặp lại:

\[
[1,3]\text{ ngày công/thay đổi}\times
[4,8]\text{ thay đổi}=[4,24]\text{ ngày công}.
\]

Ví dụ này có các giả định mạnh:

- 1–3 ngày thực sự là phần **tăng thêm do nợ**, không phải toàn bộ thời gian làm tính năng.
- Các thay đổi tương lai đủ giống những thay đổi cũ.
- Dự báo 4–8 thay đổi phản ánh roadmap, không phải số chọn tùy tiện.
- Nếu refactor, phần chậm trễ đó **có thể được giảm**, nhưng không mặc định biến mất hoàn toàn.

Vì vậy, **4–24 không phải tiền tiết kiệm chắc chắn**. Nó là khoảng minh họa cho áp lực có thể tiếp tục phải chịu nếu nợ vẫn tồn tại trong điều kiện đã nêu.

### Không gán “lãi nợ” cho mọi thời gian làm việc

Nếu một tính năng trước đây cần 5 ngày, không thể tự kết luận cả 5 ngày là lãi nợ. Một phần là công việc cần làm dù thiết kế tốt đến đâu.

Muốn ước lượng phần tăng thêm, hãy tìm dữ liệu như:

- Số vị trí phải đồng bộ quy tắc giống nhau.
- Thời gian truy tìm nguyên nhân ở lớp legacy.
- Số lần sửa hồi quy do coupling đã quan sát.
- Thời gian thiết lập môi trường/test vì thiếu ranh giới.
- Nỗ lực migration lặp lại do thiếu mô hình dữ liệu chung.

Những số liệu này không hoàn hảo, nhưng cụ thể hơn một tuyên bố “code xấu nên nhóm mất 30% năng suất”.

### Chi phí tiếp tục mang nợ không chỉ là ngày công

Còn có rủi ro lỗi sản xuất, thời gian khôi phục, chi phí vận hành và khả năng chậm giao giá trị sản phẩm. Có thể mô tả riêng **mức tác động** và **bất định về tần suất**. Không nên quy đổi mọi rủi ro thành tiền hoặc ngày công với một xác suất tự đặt.

## 10. So sánh hai khoảng không tự đưa ra đáp án

Trong ví dụ:

- **Trả nợ:** khoảng **11–31 ngày công** theo phạm vi đã mô tả.
- **Tiếp tục mang nợ trong quý:** chi phí tăng thêm **có thể khoảng 4–24 ngày công** nếu các giả định về thay đổi đúng.

Hai khoảng **chồng lấn**. Không thể kết luận “chắc chắn hoàn vốn trong quý” hoặc “chắc chắn lỗ” chỉ bằng cách so trung điểm.

Có thể thảo luận bằng các kịch bản:

| Kịch bản | Công sửa nợ | Chi phí tăng thêm nếu không sửa | Điều cần xem |
| --- | ---: | ---: | --- |
| Ít thay đổi, refactor phức tạp | Gần đầu cao | Gần đầu thấp | Trả nợ lớn có thể chưa cần ngay |
| Nhiều thay đổi, phạm vi refactor rõ | Gần đầu thấp | Gần đầu cao | Trả nợ có thể đáng ưu tiên |
| Rủi ro sản xuất cao | Bất định | Không chỉ có ngày công | Cần đánh giá hậu quả và biện pháp an toàn |
| Chưa rõ consumer/tích hợp | Khoảng rộng | Chưa rõ | Nên giảm bất định trước khi quyết định |

Không nên áp công thức ROI quen thuộc một cách máy móc khi các giả định còn sơ bộ. Nếu muốn tính kỳ vọng hoặc phân phối xác suất, cần có mô hình và dữ liệu phù hợp, đồng thời xem **tương quan** giữa các yếu tố.

Ví dụ, số thay đổi khuyến mãi nhiều có thể đồng thời làm công refactor khó hơn và làm chi phí mang nợ tăng. Không được giả sử mọi biến độc lập chỉ vì bảng tính có các ô riêng.

## 11. Không chắc chắn có thể được giảm bằng một “spike” nhỏ

Một khoảng rộng thường chứa thông tin: **có câu hỏi quan trọng chưa được trả lời**. Thay vì tranh luận giữa 18 hay 22 ngày, nhóm có thể chọn một thử nghiệm kỹ thuật ngắn.

Ví dụ spike 1–2 ngày nhằm:

1. Lập danh sách consumer của `CheckoutManager` và logic giá.
2. Xác định có hay không phụ thuộc vào schema/database.
3. Thử tách một phép tính có kiểm thử biên.
4. Chạy test tích hợp chính để phát hiện vùng thiếu bảo vệ.
5. Ghi rủi ro migration và các phụ thuộc phải phối hợp.

Kết quả có thể làm khoảng thay đổi:

```text
Trước khảo sát:
  11–31 ngày công, consumer chưa rõ.

Sau khảo sát giả định:
  14–21 ngày công, đã xác nhận ba consumer,
  test giá có thể tách độc lập, không cần đổi schema.
```

Con số sau khảo sát vẫn là **ví dụ**, không phải kết quả thực của bất kỳ repository nào. Khoảng thu hẹp chỉ hợp lý khi có bằng chứng giải quyết phần bất định cũ.

### Chọn việc khảo sát theo giá trị thông tin

Một câu hỏi tốt là: “Nếu biết câu trả lời, quyết định có đổi không?”

- Nếu việc tồn tại một consumer bên ngoài sẽ khiến kế hoạch cần thêm 10 ngày, điều tra consumer có giá trị.
- Nếu việc biết chính xác một helper dài 86 hay 91 dòng không làm đổi phạm vi, khảo sát đó ít giá trị.
- Nếu rủi ro transaction là yếu tố có thể làm rollback, cần kiểm tra ranh giới transaction trước khi tách lớp.

Không nên dành nhiều tuần đo đạc chỉ để có con số đẹp. Mục tiêu của spike là **giảm đủ bất định cho quyết định sắp tới**, chứ không loại bỏ mọi điều chưa biết.

## 12. Cập nhật khoảng khi bằng chứng thay đổi

Ước lượng là dự báo có điều kiện, không phải một con số để bảo vệ bằng mọi giá.

Sau mỗi bước đáng kể, có thể cập nhật:

| Thời điểm | Bằng chứng mới | Điều chỉnh hợp lý |
| --- | --- | --- |
| Trước khảo sát | Chưa rõ consumer | Giữ khoảng rộng và ghi giả định |
| Sau liệt kê consumer | Phát hiện hai đường tích hợp cần đổi | Điều chỉnh hạng mục tích hợp |
| Sau viết test biên | Phát hiện mã cũ xử lý sai một trường hợp | Phân biệt sửa lỗi với refactor, bổ sung phạm vi |
| Sau prototype | Tách policy không cần đổi schema | Giảm bất định migration |
| Sau rollout thử | Có lỗi mapping ở một adapter | Cập nhật công sức và kế hoạch rollback |

Không phải lần nào khoảng cũng phải **hẹp lại**. Nếu khảo sát phát hiện phụ thuộc phức tạp trước đó chưa biết, khoảng có thể rộng hơn hoặc dịch lên. Đó là dấu hiệu dự báo trở nên trung thực hơn, không phải bằng chứng người ước lượng kém.

### Không thay đổi quá khứ để làm kế hoạch có vẻ đúng

Khi báo cáo, hãy lưu lịch sử các phiên bản ước lượng cùng thời điểm và giả định. Nếu dự báo ban đầu là 11–31, sau khảo sát thành 20–35, không nên sửa hồ sơ cũ thành 20–35 rồi tuyên bố “ước lượng từ đầu đã chính xác”.

Thông tin có giá trị là **vì sao khoảng thay đổi** và nhóm sẽ học gì từ sai khác ấy.

## 13. Lập lịch khi công sức có khoảng bất định

Cần phân biệt hai đại lượng:

- **Effort:** ngày công cần thực hiện một khối lượng công việc.
- **Elapsed time:** thời gian lịch từ bắt đầu đến hoàn thành, có thể bao gồm chờ review, phụ thuộc, nghỉ, release window và khả năng song song.

Một refactor 11–31 ngày công có thể không hoàn tất trong 11–31 ngày lịch vì:

- Cần chờ xác nhận nghiệp vụ từ đội sản phẩm.
- Migration phụ thuộc cửa sổ triển khai.
- Một người hiểu hệ thống cũ là nút thắt.
- Test tích hợp hoặc môi trường staging không sẵn.
- Các bước phải tuần tự để bảo vệ tính nhất quán.

Không nên nhân chia đơn giản ngày công với số thành viên để ra ngày giao hàng. Khi cần dự báo lịch, nên xây sơ đồ phụ thuộc, năng lực thực tế và độ biến động của từng bước; nếu có đủ lịch sử, dùng phân phối thời gian hoàn thành được hiệu chỉnh.

### Cách cam kết có điều kiện

Có thể tách kế hoạch thành hai mốc:

1. **Mốc khám phá:** khảo sát dependency, test hiện có và kiểm chứng migration, sau đó cập nhật khoảng.
2. **Mốc giao thay đổi:** chỉ cam kết lịch sau khi phạm vi, phụ thuộc và phương án kiểm soát rủi ro đủ rõ.

Nếu tổ chức cần một ngày mục tiêu ngay, nên ghi đó là **mục tiêu quản lý với mức rủi ro đã chấp nhận**, không gọi nó là kết quả chắc chắn của ước lượng kỹ thuật.

## 14. Khoảng bất định và xác suất sự cố nghiêm trọng

Một số khoản nợ không được ưu tiên chỉ bằng chi phí ngày công. Ví dụ, mô hình quyền truy cập khó hiểu có thể tạo rủi ro lộ dữ liệu khi thêm endpoint mới; một luồng thanh toán thiếu idempotency có thể tạo thao tác trùng khi retry.

Trong các trường hợp này, hãy tách:

- **Hậu quả nếu lỗi xảy ra:** mức độ nghiêm trọng và ai bị ảnh hưởng.
- **Khả năng lỗi xảy ra:** bằng chứng từ sự cố, thay đổi sắp tới, test, kiến trúc.
- **Khả năng phát hiện và khôi phục:** logging, giám sát, rollback, giới hạn tác động.
- **Công sức giảm rủi ro:** khoảng sửa nhỏ, cải thiện test, thay đổi kiến trúc hoặc kiểm soát vận hành.

Nếu không có dữ liệu để ước lượng xác suất chính xác, có thể dùng mô tả định tính có lý do như “rủi ro nghiêm trọng, xác suất chưa rõ; cần đánh giá bảo mật chuyên môn”, thay vì tự gắn “17,3% khả năng sự cố”.

**Không dùng một điểm nợ đơn lẻ để làm lu mờ rủi ro hiếm nhưng hậu quả lớn.** Quyết định trong lĩnh vực bảo mật, tiền và dữ liệu có thể cần biện pháp tức thời ngay cả khi mô hình tiết kiệm ngày công chưa chứng minh được hoàn vốn.

## 15. So sánh lựa chọn: trả toàn bộ, trả từng phần hay trì hoãn

Không nhất thiết chỉ có hai lựa chọn “refactor toàn bộ” và “không làm gì”.

Giả sử mục tiêu là giúp thêm chính sách giá mà không sửa logic checkout ở nhiều nơi. Những phương án có thể là:

| Phương án | Lợi ích kỳ vọng | Rủi ro/chi phí cần ước lượng |
| --- | --- | --- |
| **Giữ nguyên, bổ sung test** | Giảm nguy cơ regression ngắn hạn | Vẫn giữ coupling và công sửa nhiều nơi |
| **Tách riêng chính sách giá** | Tập trung lý do thay đổi phổ biến nhất | Phải giữ hợp đồng với checkout, thay một số điểm gọi |
| **Refactor toàn bộ checkout** | Có thể giảm nhiều dạng coupling | Phạm vi rộng, nhiều phụ thuộc, rollback khó hơn |
| **Đợi tính năng mới rồi cải thiện trong vùng đang sửa** | Tránh sửa phần ít được dùng | Có thể phải làm dưới áp lực deadline |
| **Spike để thu hẹp bất định** | Ra quyết định có cơ sở hơn | Tốn thời gian trước khi có thay đổi sản phẩm |

Một phương án nhỏ có thể đạt đủ lợi ích với khoảng công sức dễ dự đoán hơn. Tuy nhiên, tách một phần mà tạo hai nguồn sự thật cho quy tắc giá có thể làm nợ nặng hơn. Cần xem kỹ **trạng thái chuyển tiếp** và kế hoạch xóa đường cũ.

Chọn phương án theo giá trị thực, rủi ro và thời điểm thay đổi; không coi refactor lớn là cách duy nhất để “trả hết nợ”.

## 16. Dùng ngưỡng quyết định thay vì giả vờ chắc chắn

Một kế hoạch tốt có thể đặt những điều kiện làm thay đổi lựa chọn:

```text
Quyết định: khảo sát trước.

Nếu sau khảo sát:
- Chỉ một module dùng quy tắc và không cần migration:
  ưu tiên tách chính sách giá.
- Có nhiều consumer ngoài nhóm hoặc cần đổi schema:
  tách giai đoạn, chốt test hợp đồng và kế hoạch rollout.
- Quý tới không còn yêu cầu sửa giá:
  cân nhắc giữ test và hoãn refactor rộng.
- Có rủi ro sai tiền hoặc quyền nghiêm trọng:
  ưu tiên biện pháp giảm rủi ro dù ROI ngày công chưa rõ.
```

Những **ngưỡng quyết định** khiến khoảng ước lượng trở nên hữu ích: khi thông tin thay đổi, nhóm biết hành động tiếp theo là gì. Một con số “nợ 8,7/10” không tự chỉ ra được quyết định như vậy.

### Lưu rủi ro và chủ sở hữu

Mỗi giả định quan trọng nên có người xác nhận và một hành động:

- Ai xác nhận roadmap thay đổi giá?
- Ai sở hữu contract với consumer ngoài?
- Ai kiểm tra migration có cần không?
- Ai chịu trách nhiệm chuẩn bị rollback?
- Khi nào nhóm xem lại khoảng ước lượng?

Nếu chỉ có một bảng số mà không có chủ sở hữu giả định, số liệu sẽ nhanh chóng lỗi thời.

## 17. Cách ghi mục nợ kỹ thuật trong backlog

Một mục nợ có thể được mô tả như sau:

```text
Tên:
  Tách chính sách giá khỏi CheckoutManager.

Vấn đề quan sát:
  Các PR giá gần đây thường sửa logic ở nhiều nơi.
  Có lỗi hồi quy tại điều kiện miễn phí giao hàng.

Hậu quả nếu không làm:
  Thêm tính năng giá mất nhiều công kiểm tra và dễ sai điều kiện biên.

Phạm vi đề xuất:
  Tách CartPricing; giữ nguyên API ngoài, schema và thứ tự save/send.
  Bổ sung test ở ngưỡng, overflow và lỗi lưu.

Ước lượng sơ bộ:
  11–31 ngày công cho toàn phạm vi giả định, chưa phải P90.
  Phần bất định lớn: consumer, test tích hợp, rollout.

Dữ liệu/bằng chứng:
  Gắn PR/issue/trace liên quan, người xác nhận và ngày khảo sát.

Phương án thay thế:
  Chỉ thêm test; tách policy theo từng điểm gọi; hoãn đến lúc cần sửa.

Bước tiếp:
  Spike 1–2 ngày để xác nhận consumer và các yêu cầu tương thích.

Điều kiện quyết định:
  Chọn phạm vi sau spike; cập nhật khoảng và lịch theo phụ thuộc.

Chủ sở hữu và thời điểm xem lại:
  Người phụ trách kỹ thuật, sản phẩm, mốc review đã thống nhất.
```

Đừng coi các con số trong mẫu là tình trạng của hệ thống thật. Chúng là **cách biểu diễn một cuộc thảo luận** để người quyết định thấy bằng chứng và giới hạn.

Một backlog nợ kỹ thuật tốt không chỉ gom những công việc “cần dọn code”. Nó giúp giải thích **nợ nào đang tạo chi phí thực, khi nào nó có thể cản trở kế hoạch và bằng chứng nào cần thêm trước khi hành động**.

## 18. Các sai lầm thường gặp khi ước lượng nợ

**“Một điểm số đủ để quy đổi ra ngày công.”** Cyclomatic complexity, số dòng hoặc số code smell không đo trực tiếp chi phí refactor.

**“Có hai chữ số thập phân nghĩa là dự báo đáng tin.”** Định dạng số không thay thế dữ liệu và phương pháp đo.

**“Ước lượng một khoảng nghĩa là không cam kết gì.”** Có thể cam kết bước khám phá, ngân sách, ranh giới và điều kiện cập nhật; không cần hứa một ngày chắc chắn khi chưa rõ phụ thuộc.

**“Khoảng thấp–cao chính là P10–P90.”** Khoảng kịch bản không có ý nghĩa xác suất nếu chưa được hiệu chỉnh bằng mô hình/dữ liệu.

**“Lấy trung điểm là có ước lượng tốt nhất.”** Trung điểm không tự là trung vị, kỳ vọng hoặc kết quả có khả năng cao nhất.

**“Cộng các khoảng rồi coi cận cao là không thể vượt.”** Bao ngoài dựa trên cận giả định; rủi ro chưa biết có thể làm công sức vượt mức.

**“Thêm phần trăm dự phòng chung sẽ giải quyết hết bất định.”** Dự phòng có thể hữu ích trong quản lý, nhưng không thay việc xác định phụ thuộc và kịch bản rủi ro.

**“Toàn bộ thời gian làm tính năng là lãi nợ.”** Chỉ phần chi phí **tăng thêm** vì tình trạng kỹ thuật mới thuộc phép so sánh này.

**“Tổng công sức chia cho số người là thời hạn.”** Lịch phụ thuộc trình tự, review, năng lực và thời gian chờ, không chỉ tổng ngày công.

**“Khoảng rộng chứng tỏ nhóm thiếu năng lực.”** Khoảng rộng có thể phản ánh thông tin chưa có; cần quyết định nên điều tra hay chấp nhận bất định.

**“Bắt đầu refactor luôn để khỏi tốn ngày khảo sát.”** Khi có phụ thuộc chưa rõ, một spike nhỏ có thể tránh sửa sai phạm vi; nhưng khảo sát cũng cần giới hạn.

**“Refactor xong chắc chắn không còn lãi nợ.”** Kiến trúc mới vẫn cần thay đổi, test và vận hành; lợi ích cần được quan sát sau khi triển khai.

**“Nợ ổn định không gây chi phí nên mãi mãi không cần xem.”** Một thay đổi roadmap, bảo mật hoặc phụ thuộc có thể làm rủi ro tăng nhanh; cần xem lại khi bối cảnh thay đổi.

## 19. Bài tập tình huống

### Tình huống A: điểm complexity được chuyển thành ngày công

Một dashboard báo `CheckoutManager` có cyclomatic complexity 28. Người quản lý đề xuất “vậy cần 28 ngày để trả nợ”.

Hãy giải thích vì sao phép quy đổi này không có cơ sở. Đề xuất các hạng mục phạm vi, bằng chứng và khoảng công sức có đơn vị để nhóm bắt đầu thảo luận.

### Tình huống B: hai khoảng chồng lấn

Chi phí trả nợ được ước lượng **11–31 ngày công**. Chi phí tăng thêm do tiếp tục mang nợ trong quý có thể là **4–24 ngày công**.

Có thể kết luận chắc chắn nên trả nợ ngay không? Hãy xác định ít nhất ba giả định cần kiểm tra, một bước spike có giá trị và một điều kiện khiến quyết định thay đổi.

### Tình huống C: sau khảo sát khoảng tăng

Trước khi khảo sát, nhóm ước lượng tích hợp **3–7 ngày công**. Sau đó phát hiện một hệ thống đối tác chưa có test hợp đồng, khiến phần tích hợp được ước lượng lại thành **8–15 ngày công**.

Hãy lập bảng trước–sau với lý do thay đổi. Vì sao không nên coi việc tăng khoảng là thất bại của người ước lượng? Kế hoạch và phương án rollback cần thay đổi gì?

### Tình huống D: dự báo P90 không có dữ liệu

Một thành viên đưa ba số “lạc quan 10 ngày, bình thường 15 ngày, bi quan 30 ngày” rồi báo cáo “P90 = 30 ngày”.

Hãy giải thích P90 thực sự có nghĩa gì và vì sao không thể suy ra từ ba mức kịch bản tùy ý. Nếu nhóm muốn dự báo xác suất có cơ sở, cần thu thập dữ liệu nào và kiểm tra chất lượng mô hình ra sao?

### Tình huống E: ngày công và thời gian lịch

Một công việc có khoảng **12–20 ngày công**. Nhóm có bốn người và muốn hứa giao trong 3–5 ngày lịch bằng cách chia cho bốn.

Hãy liệt kê các phụ thuộc có thể khiến lịch dài hơn, cách chia việc song song hợp lý và thông tin cần có trước khi cam kết deadline.

### Tình huống F: rủi ro bảo mật nhưng ít thay đổi

Một thư viện phân quyền ít khi được sửa nên lãi nợ ngày công gần như bằng 0. Tuy nhiên, việc bổ sung API mới có thể bỏ qua một kiểm tra quyền và hậu quả nếu xảy ra rất nghiêm trọng.

Hãy giải thích vì sao phân tích ROI ngày công chưa đủ. Đề xuất bước giảm rủi ro, khoảng công sức và cách ra quyết định khi xác suất sự cố chưa thể định lượng đáng tin.

### Tình huống G: sửa từng phần hoặc sửa toàn bộ

Nhóm đang phân vân giữa tăng test cho code cũ, tách `CartPricing` và viết lại toàn bộ checkout.

Hãy tạo bảng so sánh theo phạm vi, lợi ích mong đợi, rủi ro chuyển đổi và khoảng công sức (có thể tự giả định nhưng **phải ghi rõ là giả định**). Nêu thông tin nào cần thu thập để chọn một phương án và giới hạn nào khiến nhóm nên dừng refactor.

Với mỗi tình huống, hãy trình bày theo chuỗi: **bằng chứng hiện có → phạm vi → khoảng và đơn vị → giả định/bất định → bước giảm bất định → quyết định có điều kiện**.

## 20. Ghi nhớ

**Ước lượng nợ kỹ thuật không phải tìm một con số đẹp nhất; đó là cách diễn đạt điều nhóm biết, điều chưa biết và điều gì sẽ khiến quyết định thay đổi.**

- Phân biệt nợ kỹ thuật, lỗi cần sửa ngay, chi phí trả nợ và phần công sức tăng thêm do tiếp tục giữ nợ.
- Ghi rõ **phạm vi, đơn vị, nguồn số liệu và giả định** trước khi đưa ra khoảng ước lượng.
- Dùng khoảng kịch bản thấp–cao khi chưa có dữ liệu xác suất; đừng tự đặt nhãn P50/P90 hoặc mức tin cậy.
- Công thức tính khoảng phải đúng, nhưng dữ liệu đầu vào và nguyên nhân bất định mới quyết định độ đáng tin của dự báo.
- So sánh cả chi phí sửa, chi phí không sửa, rủi ro hậu quả lớn và lợi ích thực sự của các phương án nhỏ hơn.
- Ưu tiên spike hoặc kiểm tra nhỏ khi thông tin mới có thể làm thay đổi quyết định.
- Cập nhật ước lượng theo bằng chứng và lưu lịch sử dự báo; khoảng rộng hơn sau khám phá đôi khi lại chính xác về mặt nhận thức hơn.
- Dùng các ngưỡng quyết định, chủ sở hữu và mốc xem lại để biến ước lượng thành kế hoạch hành động.

Một bản ước lượng có **khoảng không chắc chắn và giả định rõ ràng** giúp kỹ sư, người quản lý và đội sản phẩm cùng nhìn thấy rủi ro, chọn đúng thời điểm trả nợ và tránh biến sự thiếu thông tin thành một điểm số có vẻ chính xác.
