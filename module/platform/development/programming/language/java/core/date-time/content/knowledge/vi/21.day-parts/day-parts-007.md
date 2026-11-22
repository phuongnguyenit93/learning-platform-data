# Xử lý MonthDay ngày 29 tháng 2 khi gắn một năm

## 1. Cặp tháng/ngày hợp lệ chưa chắc tồn tại trong mọi năm

`MonthDay.of(2, 29)` biểu diễn ngày 29 tháng 2 mà chưa chọn năm. Giá trị này hợp lệ, vì có những năm chứa ngày đó. Sau khi ghép với một năm, kết quả phải là một `LocalDate` thật sự tồn tại.

Đây là hai câu hỏi khác nhau:

- **Cặp tháng/ngày có thể tồn tại không?** `MonthDay` cho phép 29/2 nhưng không cho phép 30/2.
- **Cặp tháng/ngày có tồn tại trong năm đang chọn không?** Cần biết năm đó có nhuận hay không.

Điểm dễ gây lỗi nhất là cho rằng `atYear` luôn giữ nguyên ngày hoặc luôn ném ngoại lệ khi không giữ được. Hợp đồng thực tế của nó có một quy tắc điều chỉnh rõ ràng.

## 2. Hành vi mặc định của atYear

Với `MonthDay` là 29/2:

| Lời gọi | Kết quả |
| --- | --- |
| `atYear(2024)` | `2024-02-29` |
| `atYear(2023)` | `2023-02-28` |
| `atYear(2000)` | `2000-02-29` |
| `atYear(2100)` | `2100-02-28` |

`atYear` lùi về **28 tháng 2** nếu năm không nhuận. Nó không chuyển sang 1 tháng 3 và không giữ một ngày không hợp lệ trong `LocalDate`. Bản `MonthDay` ban đầu vẫn là `--02-29`, vì các giá trị này bất biến. [MonthDay.atYear](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/MonthDay.html#atYear(int))

Nếu nghiệp vụ chấp nhận quy tắc 28/2, có thể dùng thẳng `atYear`. Nếu nghiệp vụ đòi hỏi giữ đúng ngày hoặc bỏ qua năm thường, phải kiểm tra và áp dụng chính sách khác trước khi chuyển.

## 3. isValidYear để kiểm tra khả năng giữ đúng tháng/ngày

Đoạn minh họa trong một phương thức:

```java
MonthDay leapDay = MonthDay.of(2, 29);
boolean valid2024 = leapDay.isValidYear(2024); // true
boolean valid2023 = leapDay.isValidYear(2023); // false
```

Ở đây `false` nghĩa là không có đúng ngày 29/2 trong năm đó; không có nghĩa đối tượng `MonthDay` đã sai. Với một cặp thông thường như 15/8, câu hỏi năm nhuận không làm thay đổi khả năng tồn tại của ngày.

Cũng cần kiểm tra **miền số năm** khi nhận đầu vào bên ngoài. Không dùng `isValidYear` như trình xác nhận mọi ràng buộc của tham số năm: nó không thay thế việc kiểm tra giới hạn biểu diễn. Dùng `Year.of(year)` hoặc một phép tạo ngày phù hợp để xác nhận năm thuộc miền hỗ trợ.

Năm ISO nhuận khi chia hết cho 4, trừ năm chia hết cho 100 nhưng không chia hết cho 400. Dùng `Year.isLeap(year)` thay vì chỉ viết `year % 4 == 0`. Điều này giải thích vì sao 2000 nhuận còn 2100 không nhuận. [Year.isLeap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Year.html#isLeap(long))

## 4. Chọn chính sách cho năm không có 29/2

| Chính sách | Ngày ứng với năm 2023 | Dùng khi ý nghĩa yêu cầu là |
| --- | --- | --- |
| Về ngày cuối tháng Hai | `2023-02-28` | Vẫn có một ngày đại diện trong tháng Hai |
| Sang ngày đầu tháng Ba | `2023-03-01` | Chọn ngày sau 28/2 |
| Bỏ qua năm thường | Không có ngày của năm đó | Sự kiện chỉ xảy ra đúng 29/2 |
| Từ chối việc ghép năm | Báo lỗi | Dữ liệu phải giữ nguyên cặp tháng/ngày |

Đây là lựa chọn nghiệp vụ; thư viện chỉ cung cấp hành vi mặc định. Nên đặt tên chính sách trong mã thay vì để người đọc tự suy ra từ một phép cộng hoặc trừ một ngày.

“Bỏ qua” khác với “từ chối”: không có lần xuất hiện trong một năm có thể là kết quả hợp lệ của lịch lặp; một yêu cầu nhập ngày phải giữ đúng 29/2 lại có thể cần báo lỗi ngay. `Optional<LocalDate>` biểu diễn sự vắng mặt rõ hơn `null` hoặc một ngày thay thế bí mật.

## 5. Chương trình hoàn chỉnh với bốn chính sách

Lưu thành `LeapDayBindingDemo.java`. Hàm `bind` nhận mọi `MonthDay`, nhưng chỉ áp dụng chính sách đặc biệt khi tháng/ngày không tồn tại trong năm đích.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.Year;
import java.util.Objects;
import java.util.Optional;

public class LeapDayBindingDemo {
    enum MissingDatePolicy { FEBRUARY_28, MARCH_1, SKIP, REJECT }

    static Optional<LocalDate> bind(
            MonthDay value, int year, MissingDatePolicy policy) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(policy, "policy");
        Year.of(year);

        if (value.isValidYear(year)) {
            return Optional.of(value.atYear(year));
        }

        // MonthDay hợp lệ nhưng không tồn tại trong năm: chỉ có trường hợp 29/2.
        return switch (policy) {
            case FEBRUARY_28 -> Optional.of(LocalDate.of(year, 2, 28));
            case MARCH_1 -> Optional.of(LocalDate.of(year, 3, 1));
            case SKIP -> Optional.empty();
            case REJECT -> throw new DateTimeException(
                    "Month/day does not exist in target year");
        };
    }

    public static void main(String[] args) {
        MonthDay leapDay = MonthDay.of(2, 29);

        System.out.println("default2023=" + leapDay.atYear(2023));
        System.out.println("default2024=" + leapDay.atYear(2024));
        System.out.println("leap2000=" + Year.isLeap(2000));
        System.out.println("leap2100=" + Year.isLeap(2100));
        System.out.println("valid2100=" + leapDay.isValidYear(2100));

        System.out.println("february="
                + bind(leapDay, 2023, MissingDatePolicy.FEBRUARY_28));
        System.out.println("march="
                + bind(leapDay, 2023, MissingDatePolicy.MARCH_1));
        System.out.println("skip="
                + bind(leapDay, 2023, MissingDatePolicy.SKIP));
        System.out.println("leapYear="
                + bind(leapDay, 2024, MissingDatePolicy.REJECT));
        System.out.println("ordinary="
                + bind(MonthDay.of(8, 15), 2023, MissingDatePolicy.SKIP));

        try {
            bind(leapDay, 2023, MissingDatePolicy.REJECT);
        } catch (DateTimeException ex) {
            System.out.println("rejected2023");
        }

        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("strictConstructionRejected");
        }

        System.out.println("changedYear="
                + LocalDate.of(2024, 2, 29).withYear(2023));
        System.out.println("monthDayStill=" + leapDay);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 LeapDayBindingDemo.java
java LeapDayBindingDemo
```

Stdout chính xác:

```text
default2023=2023-02-28
default2024=2024-02-29
leap2000=true
leap2100=false
valid2100=false
february=Optional[2023-02-28]
march=Optional[2023-03-01]
skip=Optional.empty
leapYear=Optional[2024-02-29]
ordinary=Optional[2023-08-15]
rejected2023
strictConstructionRejected
changedYear=2023-02-28
monthDayStill=--02-29
```

`Year.of(year)` đứng trước chính sách để năm ngoài miền không bị xem là một lần xuất hiện cần bỏ qua. Nhánh `REJECT` cũng không từ chối mọi ngày: nó chỉ từ chối khi ngày cụ thể thật sự không tồn tại trong năm đích.

## 6. Tạo ngày nghiêm ngặt khác với điều chỉnh ngày có sẵn

`LocalDate.of(2023, 2, 29)` tạo một ngày cụ thể và phải kiểm tra đủ năm/tháng/ngày; nó ném `DateTimeException`. Có thể dùng cách này để thực hiện phép ghép nghiêm ngặt:

```java
LocalDate exact = LocalDate.of(
        year, monthDay.getMonthValue(), monthDay.getDayOfMonth());
```

Đây là đoạn trong một phương thức, với `year` và `monthDay` là đầu vào. Nếu muốn thông báo lỗi nghiệp vụ riêng, kiểm tra trước bằng `isValidYear` sau khi xác nhận miền năm. [LocalDate.of](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#of(int,int,int))

Ngược lại, `LocalDate.of(2024, 2, 29).withYear(2023)` là điều chỉnh một ngày có sẵn; nó chọn ngày cuối tháng hợp lệ là 28/2. Không dùng `withYear` như một phép kiểm tra yêu cầu “giữ đúng 29/2”. [LocalDate.withYear](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#withYear(int))

Sự khác biệt này giúp tránh một lỗi khó thấy: dữ liệu đầu vào vốn không hợp lệ có thể bị sửa thành một ngày hợp lệ nếu chọn nhầm API điều chỉnh.

## 7. Giữ dữ liệu gốc khi tính nhiều năm

Khi tạo các lần kỷ niệm hằng năm, hãy ghép lại từ **MonthDay gốc** cho từng năm. Không lấy kết quả đã điều chỉnh của năm trước làm nguồn cho mọi năm sau.

Ví dụ sai ý định: gắn `--02-29` vào 2023 được `2023-02-28`, rồi lấy `withYear(2024)` từ kết quả đó sẽ ra `2024-02-28`. Thông tin “ngày gốc là 29/2” đã mất khỏi ngày trung gian. Nếu ghép lại `MonthDay.of(2, 29).atYear(2024)`, kết quả đúng theo dữ liệu gốc là `2024-02-29`.

Nếu đã chuyển sang `LocalDate`, gọi `MonthDay.from(adjustedDate)` cũng chỉ khôi phục 28/2 của ngày đã điều chỉnh, không tự biết đó từng là sự kiện 29/2. Nên lưu riêng quy tắc gốc và ngày kết quả của mỗi lần xuất hiện.

Với chính sách `SKIP`, `Optional.empty()` chỉ nói năm được hỏi không có ngày; tìm lần xuất hiện kế tiếp là một tác vụ riêng, cần xét các năm tiếp theo. Không mặc định năm nhuận kế tiếp luôn cách đúng 4 năm, vì có ngoại lệ thế kỷ.

## 8. Ranh giới cần kiểm tra

- Năm nhuận thông thường như 2024 và năm thường như 2023.
- Năm tròn thế kỷ: 2000 có nhuận, 2100 không nhuận.
- Một `MonthDay` không phải 29/2: mọi chính sách phải giữ nguyên tháng/ngày khi ghép được.
- Năm ngoài miền hỗ trợ và các đầu vào `null`: báo lỗi đầu vào, không tự chuyển thành ngày thay thế.
- Tính liên tiếp nhiều năm từ dữ liệu gốc, đặc biệt năm nhuận sau một năm đã dùng 28/2.

Sau khi ghép, `LocalDate` vẫn chỉ là ngày, chưa có giờ/múi giờ. Nếu dùng kết quả để gửi lời nhắc, hãy bổ sung các quy tắc đó ở bước lập lịch; chính sách xử lý 29/2 không tự quyết định thời điểm gửi.

## 9. Tự thực hành

1. In kết quả `MonthDay.of(2, 29).atYear(2100)` và giải thích vì sao không có 29/2.
2. Áp dụng cả bốn chính sách cho `MonthDay.of(3, 15)` trong năm 2023.
3. So sánh việc ghép từ MonthDay gốc vào 2024 với việc đổi năm từ kết quả đã điều chỉnh của 2023.
4. Viết phép ghép phải báo lỗi thay vì điều chỉnh khi chọn năm thường cho 29/2.

Đối chiếu: (1) `2100-02-28`; năm 2100 chia hết cho 100 nhưng không chia hết cho 400; (2) đều cho `2023-03-15`; (3) lần lượt 29/2 và 28/2; (4) dùng chính sách `REJECT` hoặc tạo `LocalDate` trực tiếp từ đủ ba thành phần.