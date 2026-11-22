# plusYears() từ ngày nhuận và quy tắc điều chỉnh trong Java

## Mục tiêu

Phương thức `plusYears(long years)` cộng một số năm lịch vào ngày hoặc ngày giờ. Quy tắc quan trọng là **kết quả phải là một ngày hợp lệ trong tháng đích**. Khi ngày tương ứng không tồn tại, Java điều chỉnh về ngày hợp lệ cuối cùng của tháng đó thay vì giữ một ngày không hợp lệ hoặc tự động cộng thêm sang tháng kế tiếp.

Ví dụ điển hình là ngày 29/02: cộng một năm vào ngày này cho ra 28/02 năm thường. Quy tắc này dễ gây bất ngờ khi tính tuổi, ngày kỷ niệm, kỳ hạn, gia hạn hợp đồng hoặc khi nhiều lần cộng năm được nối tiếp.

Các ví dụ dưới đây dùng Java 17+ và API `java.time`.

## 1. plusYears() hoạt động trên năm lịch

Với `LocalDate`, lời gọi:

```java
LocalDate nextYear = date.plusYears(1);
```

không có nghĩa là cộng chính xác 365 ngày hoặc 365 × 24 giờ. Nó giữ tháng và ngày nếu có thể, cộng vào thành phần năm, rồi điều chỉnh ngày nếu tháng đích không có ngày đó. Năm nhuận có thể có 366 ngày; độ dài thời gian giữa hai mốc lịch do đó không phải lúc nào cũng bằng nhau.

Với ngày thông thường, kết quả giữ nguyên tháng/ngày:

```java
LocalDate date = LocalDate.of(2023, 5, 12);
System.out.println(date.plusYears(1));
```

Kết quả:

```text
2024-05-12
```

Với ngày nhuận, tháng và ngày dự kiến có thể không hợp lệ trong năm đích:

```java
LocalDate leapDay = LocalDate.of(2020, 2, 29);
System.out.println(leapDay.plusYears(1));
```

Kết quả:

```text
2021-02-28
```

Năm 2021 không phải năm nhuận, nên tháng 2 chỉ có 28 ngày. Java chọn ngày hợp lệ cuối cùng của tháng 2. Nó **không** tạo ra 2021-03-01, cũng không ném lỗi chỉ vì ngày 29/02 không tồn tại ở năm đích.

## 2. Quy tắc điều chỉnh ngày không hợp lệ

Về mặt khái niệm, phép cộng năm với ngày lịch thực hiện các bước sau:

1. Tính năm đích bằng cách cộng `years` vào năm hiện tại.
2. Giữ tháng và ngày hiện tại làm ngày dự kiến ở năm đích.
3. Nếu tổ hợp năm–tháng–ngày đó không hợp lệ, thay ngày bằng ngày hợp lệ cuối cùng của tháng đích.

Bảng ví dụ:

| Ngày ban đầu | Phép gọi | Kết quả | Lý do |
|---|---|---|---|
| `2020-02-29` | `plusYears(1)` | `2021-02-28` | Năm đích không nhuận, 29/02 không tồn tại. |
| `2020-02-29` | `plusYears(4)` | `2024-02-29` | 2024 là năm nhuận, ngày giữ nguyên được. |
| `2021-01-31` | `plusMonths(1)` | `2021-02-28` | Quy tắc tương tự áp dụng cho phép cộng tháng. |
| `2020-02-29` | `plusYears(0)` | `2020-02-29` | Không cần điều chỉnh khi ngày đích vẫn hợp lệ. |

Năm nhuận trong lịch ISO dùng bởi `LocalDate` được xác định theo quy tắc Gregorian: năm chia hết cho 4 là năm nhuận, ngoại trừ năm chia hết cho 100 thì phải chia hết cho 400 mới là năm nhuận. Vì thế 2000 là năm nhuận nhưng 1900 không phải; 2024 là năm nhuận còn 2023 và 2100 không phải.

Bạn không cần tự viết logic kiểm tra năm nhuận để dùng `plusYears()`. API ngày giờ xử lý tính hợp lệ của ngày theo lịch ISO, tránh lỗi khi tự tính số ngày của tháng.

## 3. Một phép cộng bốn năm khác với bốn phép cộng một năm

Một điểm quan trọng: `plusYears(4)` tính từ ngày gốc đến năm đích trực tiếp. Nếu chia thành nhiều bước, mỗi bước sẽ điều chỉnh ngày và kết quả điều chỉnh trở thành đầu vào cho bước sau.

```java
LocalDate original = LocalDate.of(2020, 2, 29);

LocalDate direct = original.plusYears(4);

LocalDate stepped = original;
for (int i = 0; i < 4; i++) {
    stepped = stepped.plusYears(1);
}

System.out.println("Original: " + original);
System.out.println("Direct:   " + direct);
System.out.println("Stepped:  " + stepped);
```

Kết quả:

```text
Original: 2020-02-29
Direct:   2024-02-29
Stepped:  2024-02-28
```

Diễn biến từng bước của phép cộng dồn:

| Bước | Phép tính | Kết quả |
|---|---|---|
| 0 | Ngày gốc | `2020-02-29` |
| 1 | `2020-02-29.plusYears(1)` | `2021-02-28` |
| 2 | `2021-02-28.plusYears(1)` | `2022-02-28` |
| 3 | `2022-02-28.plusYears(1)` | `2023-02-28` |
| 4 | `2023-02-28.plusYears(1)` | `2024-02-28` |

Ở bước đầu, ngày 29 đã được điều chỉnh thành ngày 28. Các lần cộng sau giữ ngày 28, vì đối tượng không còn lưu rằng ngày gốc từng là 29/02. Khi cần ngày tương ứng sau bốn năm kể từ mốc gốc, gọi `original.plusYears(4)`. Khi nghiệp vụ yêu cầu từng kỳ hằng năm nối tiếp từ ngày điều chỉnh thực tế của kỳ trước, lặp `plusYears(1)` có thể đúng hơn. Hãy chọn dựa theo ý nghĩa nghiệp vụ, không chỉ theo hình thức vòng lặp.

## 4. Ví dụ đầy đủ: điều chỉnh ngày nhuận

Tạo tệp `LeapDayPlusYearsDemo.java`:

```java
import java.time.LocalDate;

public class LeapDayPlusYearsDemo {
    public static void main(String[] args) {
        LocalDate leapDay = LocalDate.of(2020, 2, 29);

        LocalDate oneYearLater = leapDay.plusYears(1);
        LocalDate fourYearsLater = leapDay.plusYears(4);

        LocalDate cumulative = leapDay;
        for (int i = 0; i < 4; i++) {
            cumulative = cumulative.plusYears(1);
        }

        System.out.println("Start:       " + leapDay);
        System.out.println("Plus 1 year: " + oneYearLater);
        System.out.println("Plus 4 years:" + fourYearsLater);
        System.out.println("Cumulative:  " + cumulative);
    }
}
```

Biên dịch và chạy:

```bash
javac LeapDayPlusYearsDemo.java
java LeapDayPlusYearsDemo
```

Đầu ra:

```text
Start:       2020-02-29
Plus 1 year: 2021-02-28
Plus 4 years:2024-02-29
Cumulative:  2024-02-28
```

Dấu cách trong output là một phần của chuỗi được truyền cho `println`: dòng `Plus 4 years:` không có dấu cách cuối chuỗi, nên ngày in ngay sau dấu hai chấm. Nếu muốn dễ đọc hơn, hãy thêm một dấu cách sau dấu hai chấm trong câu lệnh in.

## 5. plusYears() không thay đổi đối tượng ban đầu

Các kiểu `java.time` như `LocalDate`, `LocalDateTime` và `ZonedDateTime` là immutable. Phương thức `plusYears()` trả về một đối tượng mới; nó không sửa đối tượng nhận lời gọi.

```java
LocalDate original = LocalDate.of(2020, 2, 29);
LocalDate adjusted = original.plusYears(1);

System.out.println(original);
System.out.println(adjusted);
```

Kết quả:

```text
2020-02-29
2021-02-28
```

Một lỗi phổ biến là gọi `date.plusYears(1)` nhưng không lưu kết quả, rồi mong `date` tự đổi. Phải gán kết quả lại nếu muốn biến tham chiếu hiện tại trỏ đến giá trị mới:

```java
date = date.plusYears(1);
```

Việc gán lại một biến tham chiếu không làm thay đổi đối tượng cũ; nó chỉ cập nhật giá trị biến để trỏ sang đối tượng mới.

## 6. LocalDateTime: ngày được điều chỉnh, giờ được giữ

Với `LocalDateTime`, quy tắc điều chỉnh ngày giống `LocalDate`; thành phần giờ, phút, giây và nano giây vẫn được giữ nguyên.

```java
LocalDateTime meeting =
        LocalDateTime.of(2020, 2, 29, 9, 45, 30);

System.out.println(meeting.plusYears(1));
```

Kết quả:

```text
2021-02-28T09:45:30
```

Ở đây không có múi giờ, offset hay thời điểm UTC gắn với đối tượng. `LocalDateTime.plusYears(1)` xử lý lịch địa phương; nó không thể tự quyết định ảnh hưởng của DST hoặc chuyển sang một thời điểm tuyệt đối.

Nếu ứng dụng đang lên lịch một sự kiện “09:45 theo giờ địa phương”, hãy lưu hoặc xử lý vùng thời gian riêng theo nhu cầu. Đừng suy ra rằng `LocalDateTime` là một timestamp toàn cầu chỉ vì nó có đủ ngày và giờ.

## 7. ZonedDateTime: phép cộng năm theo lịch vùng

`ZonedDateTime.plusYears()` cũng áp dụng phép cộng năm lịch và điều chỉnh ngày không hợp lệ. Tuy nhiên, `ZonedDateTime` có `ZoneId` và offset; nếu quy tắc múi giờ tại thời điểm mới khác đi, giờ địa phương và offset cần được giải quyết theo quy tắc vùng.

Ví dụ ngày nhuận ở một vùng:

```java
ZonedDateTime start = ZonedDateTime.of(
        2020, 2, 29, 9, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime nextYear = start.plusYears(1);
System.out.println(nextYear);
```

Trong ngày đích là 28/02/2021, giờ địa phương 09:00 vẫn hợp lệ và được giữ. Offset được tính theo quy tắc của `Europe/Paris` cho ngày đích; không nên hard-code offset năm 2020 cho tất cả năm sau.

Cộng một năm lịch vào `ZonedDateTime` không tương đương với cộng một số giây cố định. Nếu yêu cầu nghiệp vụ là “sau đúng 365 × 24 giờ”, hãy tính theo thời lượng như `Duration`. Nếu yêu cầu là “cùng ngày và giờ địa phương vào năm tới”, dùng phép tính lịch như `plusYears(1)` và định nghĩa chính sách cho các trường hợp ngày bị điều chỉnh.

## 8. Khi nào điều chỉnh 29/02 là đúng với nghiệp vụ?

Không có một chính sách ngày nhuận duy nhất phù hợp cho mọi hệ thống. `plusYears()` cung cấp hành vi ổn định: điều chỉnh về ngày cuối tháng khi ngày gốc không tồn tại trong tháng đích. Nhưng ứng dụng nên xác định xem đó có đúng với quy tắc kinh doanh không.

| Nghiệp vụ | Câu hỏi cần xác định | Cách tiếp cận |
|---|---|---|
| Sinh nhật/ngày kỷ niệm của người sinh 29/02 | Tổ chức vào 28/02 hay 01/03 trong năm thường? | Quy định chính sách theo sản phẩm/pháp lý; không để mặc định API quyết định ý nghĩa nghiệp vụ. |
| Gia hạn hợp đồng theo ngày lịch | Ngày đến hạn rơi vào ngày nào nếu không có 29/02? | Ghi rõ điều khoản điều chỉnh ngày; kiểm thử các ngày cuối tháng. |
| Chu kỳ tính toán tính từ ngày gốc | Cần mốc sau N năm trực tiếp hay chuỗi mốc từng năm? | Dùng `original.plusYears(n)` cho mốc từ gốc; dùng cộng dồn khi mỗi kỳ sau bắt đầu từ kỳ trước. |
| Lịch nhắc hằng năm theo giờ địa phương | Giờ địa phương và múi giờ có cần giữ không? | Dùng kiểu lịch phù hợp, thường là ngày/giờ địa phương kèm `ZoneId`, và xác định quy tắc DST. |

Nếu nghiệp vụ yêu cầu ngày 01/03 trong năm thường cho mốc 29/02, `plusYears()` không trực tiếp thể hiện chính sách đó. Bạn cần viết quy tắc nghiệp vụ riêng và kiểm thử rõ ràng; không nên giả định API sẽ tự chuyển tới 01/03.

## 9. Kiểm thử quy tắc ngày nhuận

Một số kiểm thử nên có trong ứng dụng xử lý ngày lịch:

- Ngày 29/02 của năm nhuận cộng 1 năm sang năm thường.
- Ngày 29/02 cộng 4 năm đến năm nhuận tiếp theo.
- Trường hợp năm thế kỷ như 1900 và 2000 theo lịch ISO.
- Cộng nhiều lần mỗi lần một năm so với một lần cộng N năm.
- Ngày cuối tháng khác như 31/01 khi cộng tháng, nếu hệ thống dùng cả `plusMonths()`.
- `LocalDateTime` và `ZonedDateTime` để chắc chắn giờ địa phương/múi giờ được xử lý theo đúng kỳ vọng.

Ví dụ kiểm tra đơn giản bằng assertion:

```java
import java.time.LocalDate;

public class LeapDayAssertions {
    public static void main(String[] args) {
        LocalDate leapDay = LocalDate.of(2020, 2, 29);

        if (!leapDay.plusYears(1).equals(LocalDate.of(2021, 2, 28))) {
            throw new AssertionError("Year adjustment failed");
        }

        if (!leapDay.plusYears(4).equals(LocalDate.of(2024, 2, 29))) {
            throw new AssertionError("Leap year restoration failed");
        }

        System.out.println("All checks passed");
    }
}
```

Biên dịch và chạy:

```bash
javac LeapDayAssertions.java
java LeapDayAssertions
```

Đầu ra khi các kiểm tra đúng:

```text
All checks passed
```

Các assertion này không phụ thuộc múi giờ hệ thống vì chỉ dùng `LocalDate`. Với logic dựa trên `ZonedDateTime`, truyền rõ `ZoneId` thay vì dùng cấu hình mặc định của máy để kết quả kiểm thử có thể tái lập.

## 10. Lỗi thường gặp

1. **Cho rằng cộng một năm tương đương 365 ngày.** Độ dài năm lịch có thể 365 hoặc 366 ngày; dùng `plusYears()` cho phép tính theo năm lịch.
2. **Nghĩ `plusYears()` sẽ luôn giữ được ngày trong tháng.** Ngày đích không tồn tại sẽ được điều chỉnh về ngày cuối tháng.
3. **Cộng dồn nhưng mong kết quả như tính từ ngày gốc.** Ngày đã bị điều chỉnh thành 28/02 sẽ tiếp tục là ngày 28 khi cộng năm từng bước. Lưu mốc gốc nếu phải tính từng mốc độc lập.
4. **Quên gán kết quả.** Các lớp `java.time` là immutable; kết quả phải được nhận qua biến.
5. **Tự xử lý năm nhuận bằng số ngày cố định.** Dùng `LocalDate` và phép tính lịch để tận dụng quy tắc chuẩn đã có.
6. **Dùng LocalDateTime như một thời điểm tuyệt đối.** Kiểu này không có offset hoặc vùng; với sự kiện toàn cầu cần dùng `Instant` hoặc kiểu phù hợp chứa offset/vùng.
7. **Không thống nhất chính sách cho ngày kỷ niệm 29/02.** Quy tắc kỹ thuật có thể xác định ngày hợp lệ, nhưng quyết định nghiệp vụ cần được mô tả riêng.

## 11. Tự kiểm tra

**Câu 1.** `LocalDate.of(2020, 2, 29).plusYears(1)` trả về ngày nào?

**Đáp án:** `2021-02-28`, vì 2021 không có ngày 29/02 và Java điều chỉnh về ngày cuối tháng.

**Câu 2.** Vì sao `2020-02-29.plusYears(4)` (tính trực tiếp từ ngày gốc) khác với việc gọi `plusYears(1)` bốn lần?

**Đáp án:** Tính trực tiếp đến 2024 giữ ngày 29/02 vì 2024 là năm nhuận. Khi cộng từng năm, bước đầu đã đổi ngày thành 28/02; các bước sau tiếp tục sử dụng ngày 28.

**Câu 3.** `plusYears(1)` có cộng chính xác 365 × 24 giờ không?

**Đáp án:** Không. Đây là phép tính lịch; số ngày và thời lượng thực phụ thuộc khoảng năm, cũng như múi giờ nếu dùng `ZonedDateTime`.

**Câu 4.** `date.plusYears(1)` có sửa đối tượng `date` không?

**Đáp án:** Không. Nó trả về một đối tượng mới. Cần viết `date = date.plusYears(1)` nếu muốn biến trỏ đến kết quả.

**Câu 5.** Nếu nghiệp vụ quy định người sinh ngày 29/02 mừng sinh nhật vào 01/03 trong năm thường, nên dựa hoàn toàn vào `plusYears()` không?

**Đáp án:** Không. Mặc định `plusYears()` điều chỉnh về 28/02. Quy tắc 01/03 phải được biểu diễn tường minh theo yêu cầu nghiệp vụ.

---

**Ghi nhớ:** `plusYears()` thực hiện phép cộng theo lịch và tự điều chỉnh ngày không hợp lệ về cuối tháng. Với ngày nhuận, hãy phân biệt mốc tính trực tiếp từ ngày gốc với cộng dồn từng kỳ, và xác nhận chính sách ngày 29/02 phù hợp với nghiệp vụ của bạn.