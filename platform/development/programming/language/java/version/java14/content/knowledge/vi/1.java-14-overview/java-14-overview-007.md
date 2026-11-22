# Kiểm chứng hành vi bằng ví dụ nhỏ và dữ liệu biên (Java 14)

## Mục tiêu

Sau bài này, bạn có thể: (1) chuyển một mô tả hành vi thành các kết quả mong đợi kiểm chứng được; (2) tạo ví dụ Java ngắn, chạy độc lập để phân biệt hành vi đúng và sai; (3) chọn dữ liệu thông thường, sát biên và ngoài miền hợp lệ; (4) kiểm tra cả giá trị trả về lẫn ngoại lệ; (5) lưu bằng chứng đủ rõ để tái hiện và sửa lỗi.

Đây là kỹ năng áp dụng lâu dài cho Java. Ví dụ chính dùng **switch expression**, cú pháp được chuẩn hóa trong Java 14 và vẫn được hỗ trợ trên các JDK hiện đại. Bài không phụ thuộc tính năng preview hay API đã lỗi thời.

## 1. Kiểm chứng hành vi là kiểm chứng điều gì?

**Hành vi quan sát được** là những gì chương trình cam kết với đầu vào và trạng thái cụ thể: giá trị trả về, ngoại lệ, thay đổi dữ liệu, đầu ra hoặc tác dụng phụ. Khi kiểm chứng, cần tách ba thứ:

- **Quy tắc mong đợi (contract):** do yêu cầu bài toán hoặc đặc tả API xác định, không suy ra bằng cách chép lại thuật toán đang kiểm tra.
- **Đầu vào và điều kiện chạy:** giá trị, kiểu dữ liệu, trạng thái trước khi gọi, phiên bản JDK và các phụ thuộc có liên quan.
- **Kết quả thực tế:** giá trị, kiểu ngoại lệ, thông điệp (nếu là một phần của contract), trạng thái sau khi gọi và bằng chứng chạy.

Một chương trình in ra kết quả trông hợp lý chưa đủ chứng minh đúng. Kiểm chứng hữu ích phải trả lời: **Với đầu vào X, kết quả nào được mong đợi, vì sao, và điều gì sẽ làm phép kiểm chứng thất bại?**

Ví dụ: hàm nhận thứ trong tuần theo quy ước ISO từ 1 (thứ Hai) đến 7 (Chủ nhật). Hợp đồng của ta quy định 1–5 là ngày làm việc, 6–7 là cuối tuần, còn số ngoài 1–7 phải ném `IllegalArgumentException`. Kết quả “0 là ngày làm việc” là lỗi ngay cả khi hàm vẫn chạy không có ngoại lệ.

## 2. Cách thiết kế một phép kiểm chứng nhỏ, có sức phát hiện lỗi

1. **Viết contract trước.** Nêu miền giá trị hợp lệ, đầu ra/ngoại lệ tương ứng, quy tắc với giá trị không hợp lệ và liệu hàm có được thay đổi đầu vào hay trạng thái hay không. Nếu đặc tả chưa rõ (ví dụ ngày 0 được chuẩn hóa hay bị từ chối), làm rõ trước khi chọn expected.
2. **Chia đầu vào thành nhóm tương đương.** Các giá trị dự kiến đi qua cùng quy tắc có thể lấy vài đại diện, nhưng phải giữ các điểm chuyển nhánh. Với ngày ISO: 1–5, 6–7, nhỏ hơn 1 và lớn hơn 7.
3. **Chọn sát biên.** Với miền nguyên đóng [min, max], ưu tiên `min − 1`, `min`, `min + 1`, `max − 1`, `max`, `max + 1` *khi các giá trị đó biểu diễn được bằng kiểu đang dùng*. Điểm đổi nhóm nội bộ cũng là biên: 5/6 trong ví dụ ngày.
4. **Tạo ví dụ tối thiểu có thể chạy.** Một lớp, một hàm cần thử, vài dữ liệu cố định và phép đối chiếu rõ ràng thường đủ để tái hiện một vấn đề. Loại bỏ nhập bàn phím, mạng, cơ sở dữ liệu, thời gian thực hoặc trạng thái ngẫu nhiên nếu không phải đối tượng kiểm chứng.
5. **Đặt expected độc lập với actual.** Không gọi lại chính hàm đang kiểm tra để tính expected. Khi kết quả sai, phép kiểm chứng phải thất bại rõ ràng, ví dụ ném `AssertionError`.
6. **Chạy, đối chiếu và tái hiện.** Ghi lệnh chạy, phiên bản JDK khi cần, đầu vào gây lỗi, expected, actual hoặc stack trace. Sau khi sửa, chạy lại cả dữ liệu vừa gây lỗi và các dữ liệu đại diện đã đúng trước đó.

Cần **ít ví dụ nhưng có chủ đích**, chứ không phải chỉ một đầu vào “đẹp”. Các ca kiểm chứng ở đường biên thường phát hiện lỗi so sánh `<`/`<=`, đảo nhóm, bỏ sót `default`, xử lý ngoại lệ hoặc tràn số.

## 3. Ví dụ hoàn chỉnh: kiểm chứng switch expression của Java 14

### Hợp đồng và bộ ca

Xây dựng phương thức `classifyIsoDay(int day)`:

| Đầu vào | Kết quả mong đợi | Vai trò |
| --- | --- | --- |
| `1` | `WORKDAY` | Biên dưới hợp lệ |
| `5` | `WORKDAY` | Ngay trước ranh giới đổi nhóm |
| `6` | `WEEKEND` | Ngay sau ranh giới đổi nhóm |
| `7` | `WEEKEND` | Biên trên hợp lệ |
| `0` | `IllegalArgumentException` | Ngay dưới miền hợp lệ |
| `8` | `IllegalArgumentException` | Ngay trên miền hợp lệ |
| `-1` | `IllegalArgumentException` | Một đầu vào âm khác |

Ví dụ này kiểm chứng giá trị trả về và **chủ động xác nhận ngoại lệ mong đợi**; ngoại lệ đúng loại trong một ca không hợp lệ là PASS. Thông điệp ngoại lệ cũng được đối chiếu vì *contract của ví dụ này* quy định nó; với API khác, chỉ bắt buộc kiểm tra thông điệp nếu đặc tả thực sự cam kết.

Tạo tệp **`BoundaryChecks.java`**:

```java
public final class BoundaryChecks {
    private BoundaryChecks() {
    }

    // Contract: 1..5 => WORKDAY, 6..7 => WEEKEND,
    // other integers => IllegalArgumentException.
    static String classifyIsoDay(int day) {
        return switch (day) {
            case 1, 2, 3, 4, 5 -> "WORKDAY";
            case 6, 7 -> "WEEKEND";
            default -> throw new IllegalArgumentException(
                    "isoDay must be from 1 to 7: " + day);
        };
    }

    private static void expectType(int day, String expected) {
        String actual = classifyIsoDay(day);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "day=" + day + ", expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println("PASS day=" + day + " -> " + actual);
    }

    private static void expectInvalid(int day) {
        String expectedMessage = "isoDay must be from 1 to 7: " + day;
        try {
            classifyIsoDay(day);
            throw new AssertionError(
                    "Expected IllegalArgumentException for day=" + day);
        } catch (IllegalArgumentException ex) {
            if (!expectedMessage.equals(ex.getMessage())) {
                throw new AssertionError(
                        "Wrong exception message for day=" + day, ex);
            }
            System.out.println(
                    "PASS day=" + day + " -> IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        expectType(1, "WORKDAY");
        expectType(5, "WORKDAY");
        expectType(6, "WEEKEND");
        expectType(7, "WEEKEND");
        expectInvalid(0);
        expectInvalid(8);
        expectInvalid(-1);
        System.out.println("ALL 7 CHECKS PASSED");
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp, với **JDK 17+**:

```bash
javac --release 14 BoundaryChecks.java
java BoundaryChecks
```

Lệnh `--release 14` yêu cầu trình biên dịch dùng mức ngôn ngữ và tập API tương thích Java 14 cho ví dụ này. Nó **không thay thế** việc chạy thực tế trên JDK 14 nếu bạn đang nghiên cứu khác biệt runtime giữa các phiên bản. Nếu đang sử dụng trực tiếp JDK 14, có thể chạy `javac BoundaryChecks.java` rồi `java BoundaryChecks`.

**Stdout mong đợi:**

```text
PASS day=1 -> WORKDAY
PASS day=5 -> WORKDAY
PASS day=6 -> WEEKEND
PASS day=7 -> WEEKEND
PASS day=0 -> IllegalArgumentException
PASS day=8 -> IllegalArgumentException
PASS day=-1 -> IllegalArgumentException
ALL 7 CHECKS PASSED
```

### Vì sao ví dụ chứng minh được điều cần kiểm tra?

- `switch` **trả về giá trị**; các nhánh mũi tên `->` không bị rơi xuyên qua nhánh tiếp theo (fall-through). Đây là hành vi ổn định của switch expression từ Java 14.
- `5` và `6` nằm hai phía điểm đổi nhóm; chỉ thử `2` và `7` sẽ dễ bỏ sót lỗi phân loại tại ranh giới.
- `0` và `8` sát hai đầu miền được phép; thêm `-1` giúp kiểm tra cả nhóm số âm.
- `expectType` dùng chuỗi expected cố định, không lấy expected bằng cách gọi lại `classifyIsoDay`. Sai khác sẽ dừng chương trình bằng `AssertionError`.
- `expectInvalid` sẽ thất bại nếu hàm *không ném* ngoại lệ hoặc ném ngoại lệ có thông điệp khác quy định. Một loại ngoại lệ không đúng cũng làm phép kiểm chứng thất bại thay vì được coi là PASS.
- Dòng `ALL 7 CHECKS PASSED` chỉ được thực thi sau khi cả bảy ca hoàn tất. Đây là bằng chứng chạy của **bảy ca đã định nghĩa**, không phải bằng chứng rằng mọi đầu vào khả dĩ đều đã được kiểm tra.

**Thử cố ý gây lỗi:** đổi `case 6, 7` thành chỉ `case 7`, và để `6` rơi vào `default`. Chạy lại; ca `expectType(6, "WEEKEND")` sẽ thất bại. Khôi phục mã đúng sau thí nghiệm. Một phép kiểm chứng tốt phải phát hiện được lỗi mà nó tuyên bố bảo vệ.

## 4. Chọn dữ liệu biên theo từng kiểu bài toán

Không áp dụng cùng một bảng dữ liệu cho mọi API. Biên có thể là giới hạn số học, thay đổi điều kiện, độ dài, trạng thái hay một trường hợp đặc biệt của kiểu dữ liệu.

| Kiểu dữ liệu / hành vi | Ca tiêu biểu | Điều cần xác nhận |
| --- | --- | --- |
| Số nguyên giới hạn `0..100` | `-1, 0, 1, 99, 100, 101` | Điều kiện biên bao gồm hay loại trừ đầu mút; quy định với giá trị ngoài miền |
| Tràn số nguyên | `Integer.MAX_VALUE + 1` | Phép cộng `int` có thể tràn và quay vòng; nếu contract yêu cầu phát hiện tràn, dùng `Math.addExact` và kiểm tra `ArithmeticException` |
| Số nguyên nhỏ nhất | `Integer.MIN_VALUE` | `Math.abs(Integer.MIN_VALUE)` vẫn âm vì trị tuyệt đối toán học không biểu diễn được trong `int`; cân nhắc mở rộng sang `long` trước khi lấy trị tuyệt đối |
| Chuỗi | `null`, `""`, `" "`, một ký tự, Unicode | Phân biệt không có đối tượng, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng; `isEmpty()` khác `isBlank()` |
| Tập hợp / mảng | Rỗng, 1 phần tử, nhiều phần tử, chỉ số `-1` hoặc `size` | Hành vi tìm kiếm, truy cập sai chỉ số, cập nhật dữ liệu, thứ tự phần tử |
| Kiểu thực | `0.0`, `-0.0`, `NaN`, vô cực, số gần ngưỡng | Không so sánh gần bằng bằng `==` trong phép tính có sai số; `NaN == NaN` là `false` |
| Ngày / thời gian | Cuối tháng, năm nhuận, thời điểm chuyển ngày hoặc múi giờ | Dùng `java.time`; xác định rõ zone và quy tắc hợp lệ, không phụ thuộc đồng hồ máy khi không cần |
| Tham số đối tượng | `null` và đối tượng hợp lệ | API cho phép `null` hay ném ngoại lệ? Đừng tự suy đoán; xem contract |
| Dữ liệu bất biến | Danh sách tạo bởi `List.of(...)` | Không cho sửa cấu trúc, không nhận phần tử `null`; kiểm tra ngoại lệ nếu đó là yêu cầu của bài toán |
| Trạng thái / thứ tự thao tác | Gọi một lần, lặp lại, gọi sai thứ tự | Kết quả có phụ thuộc trạng thái ban đầu, thay đổi ngoài ý muốn hoặc dữ liệu dùng chung không? |

Hai ví dụ rất nhỏ về biên số nguyên (API này vẫn hiện hành):

```java
int wrapped = Integer.MAX_VALUE + 1;
// wrapped == Integer.MIN_VALUE (tràn số của int)

long safe = Math.abs((long) Integer.MIN_VALUE);
// safe == 2147483648L

// Math.addExact(Integer.MAX_VALUE, 1)
// sẽ ném ArithmeticException thay vì im lặng tràn.
```

Đây là **đoạn minh họa**, không phải chương trình Java độc lập: có thể đặt vào một phương thức nếu muốn thử. Chú ý ép sang `long` **trước** khi gọi `Math.abs`; nếu gọi `Math.abs(int)` trước rồi mới ép kiểu, giá trị đã sai từ bước trước.

Với biên số học, đừng tính `max + 1` bằng chính kiểu dữ liệu mà nó không biểu diễn được nếu mục tiêu là xây dựng giá trị mong đợi. Hãy dùng kiểu rộng hơn (khi đủ sức chứa), `BigInteger`, hoặc xác nhận ngoại lệ theo contract.

## 5. Từ ví dụ tái hiện đến kiểm thử đáng tin

**Ví dụ nhỏ để tái hiện lỗi (minimal reproducer)** nên chỉ chứa dữ liệu gây lỗi, lời gọi đang xét và phép kiểm tra có thể thất bại. Khi mã thực tế có nhiều lớp, hãy rút gọn từng phần nhưng giữ nguyên điều kiện cần để lỗi xuất hiện. Ghi giá trị đầu vào thật, thay vì chỉ ghi “thỉnh thoảng lỗi”.

**Đối chiếu không chỉ bằng mắt:** `System.out.println` giúp quan sát, nhưng không thay thế assert. Từ khóa Java `assert` bị tắt theo mặc định nếu không chạy với `-ea`. Vì thế mã ví dụ chủ động ném `AssertionError`; nó kiểm tra được khi chạy bằng lệnh `java BoundaryChecks` như hướng dẫn. Trong dự án thực tế, có thể chuyển cùng contract và bảng dữ liệu sang JUnit Jupiter bằng parameterized tests và `assertThrows`; khi dùng framework cần khai báo dependency và chạy bằng test runner của dự án.

**Phân loại lỗi sau khi kiểm tra:** nếu actual khác expected, tìm xem sai ở đặc tả, dữ liệu thử, phép so sánh hay mã cần kiểm tra. Không sửa expected chỉ để phép kiểm tra có màu xanh. Với ngoại lệ, đọc cả loại ngoại lệ và vị trí phát sinh trong stack trace; đôi khi lỗi xuất hiện ở bước chuẩn bị dữ liệu chứ không phải nhánh đang xét.

**Kiểm tra tính tái hiện:** ghi `java -version`, lệnh biên dịch/chạy, một tệp nguồn ngắn và kết quả thực tế. Khi phụ thuộc phiên bản JDK, hãy kiểm tra riêng ở đúng runtime cần hỗ trợ. Thử trên nhiều phiên bản chỉ có ý nghĩa nếu hành vi hoặc khả năng tương thích là một phần của yêu cầu.

**Bổ sung sau khi đã có kiểm tra nhỏ:** tích hợp vào bộ kiểm thử tự động, thêm regression test cho lỗi vừa sửa, chạy kiểm thử với các nhóm dữ liệu khác và kiểm chứng tác dụng phụ nếu có. Ví dụ nhỏ không thay được kiểm thử tích hợp, kiểm thử đồng thời, hiệu năng hay bảo mật khi các thuộc tính ấy nằm trong yêu cầu.

## 6. Những sai lầm thường gặp và cách tránh

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Chỉ thử một giá trị bình thường | Bỏ sót điều kiện `<=`/`<`, phân nhánh sát biên | Thử ngay dưới, đúng tại và ngay trên biên |
| Không xác định expected trước khi chạy | Dễ coi kết quả bất kỳ là “đúng” | Viết contract và bảng expected độc lập |
| Bắt `Exception` quá rộng rồi coi là PASS | Có thể che giấu lỗi khác bản chất | Kiểm tra đúng kiểu ngoại lệ và thông tin contract yêu cầu |
| Chỉ in kết quả ra console | Không tự động báo lỗi khi expected khác actual | Dùng phép so sánh và assert hoạt động chắc chắn |
| Lẫn `null` với `""` hoặc chuỗi trắng | Dễ gây `NullPointerException` hoặc phân loại sai | Tách rõ các nhóm theo hợp đồng của API |
| Phụ thuộc thời gian, locale hoặc dữ liệu ngẫu nhiên | Kết quả không lặp lại ổn định | Cố định đầu vào; cấp `Clock`/`ZoneId` khi cần |
| Khẳng định tương thích JDK chỉ nhờ biên dịch | Biên dịch không xác nhận hành vi runtime | Chạy trên runtime thực tế cần hỗ trợ khi có yêu cầu |
| Sao chép output mong đợi từ output thực tế | Kiểm tra không có khả năng bắt lỗi | Tính expected từ quy tắc nghiệp vụ/đặc tả độc lập |
| Chỉnh nhiều thứ trước khi chạy lại | Khó xác định sửa đổi nào làm thay đổi kết quả | Sửa nhỏ, chạy lại ca gây lỗi và bộ ca đại diện |

## 7. Bài tự luyện và tiêu chí hoàn thành

Hãy tự viết hàm `shippingFee(int itemCount)` theo contract ví dụ: số lượng `< 0` ném `IllegalArgumentException`; `0` trả về `0`; `1..4` trả về `20_000`; từ `5` trở lên trả về `0`. Soạn bảng expected **trước** khi code và kiểm chứng ít nhất các ca `-1, 0, 1, 4, 5, 6`. Nếu người dùng có thể truyền số lượng rất lớn, hãy kiểm tra thêm `Integer.MAX_VALUE`; tránh thao tác số học không cần thiết có thể tràn. Đây là bài thực hành đặt contract và kiểm tra đúng ngưỡng, không phải quy tắc phí vận chuyển ngoài đời.

Một bài kiểm chứng đạt yêu cầu khi có đủ:

- Contract nói rõ đầu vào hợp lệ/không hợp lệ, kết quả và ngoại lệ mong đợi.
- Ít nhất một ca bình thường, các ca sát mọi biên quan trọng và ca sai đầu vào phù hợp với kiểu dữ liệu.
- Mã ngắn có thể biên dịch/chạy, phép đối chiếu tự báo thất bại và stdout hoặc kết quả test tái hiện được.
- Expected độc lập với phần đang kiểm tra; khi cố ý đưa một lỗi vào nhánh biên, test liên quan phải phát hiện.
- Nếu thay đổi mã, chạy lại ca gây lỗi và các ca đã đúng; nếu yêu cầu phụ thuộc runtime, ghi và kiểm tra phiên bản JDK cần hỗ trợ.

Tư duy cốt lõi: **mỗi ví dụ nhỏ phải trả lời một câu hỏi rõ ràng; mỗi dữ liệu biên phải nhắm đến một giả định dễ sai; mỗi PASS phải có phép đối chiếu thực sự.**