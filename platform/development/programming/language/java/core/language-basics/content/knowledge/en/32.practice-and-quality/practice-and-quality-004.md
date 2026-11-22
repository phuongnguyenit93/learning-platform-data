# Chú thích lý do và viết tài liệu cho phương thức khi cần (Java 17+)

## 1. Mục tiêu của chú thích và tài liệu

Mã Java cần đủ rõ để người đọc hiểu **chương trình đang làm gì**; chú thích (`comment`) và tài liệu phương thức giúp giải thích những điều **khó suy ra chỉ từ mã**: lý do một quyết định được đưa ra, giả định nội bộ, giới hạn, hợp đồng với người gọi, tác dụng phụ và hành vi khi gặp lỗi.

Nguyên tắc thực hành:

- **Đặt tên biến, lớp và phương thức rõ ràng trước.** `calculateTotal()` dễ hiểu hơn `calc()`, `isEligible` dễ hiểu hơn `flag`.
- **Chú thích “vì sao” ở chỗ có quyết định không hiển nhiên**, như một ngưỡng theo nghiệp vụ hoặc lý do dùng khoảng nửa mở. Không chép lại từng dòng lệnh bằng văn xuôi.
- **Dùng Javadoc khi phương thức cần mô tả hợp đồng cho người gọi**, nhất là API public, hành vi có điều kiện, tham số có giới hạn, kết quả đặc biệt hoặc ngoại lệ cần dự đoán.
- **Giữ nội dung đúng với mã.** Chú thích sai còn nguy hiểm hơn không có chú thích: nó khiến người bảo trì tin vào hành vi không còn tồn tại.
- **Đừng thay kiểm tra và tên tốt bằng chú thích dài.** Chú thích không thực thi, không kiểm tra dữ liệu, không bảo đảm điều kiện luôn đúng.

Bài học này tập trung vào mã Java core và tài liệu ở cấp phương thức. Javadoc dùng để công bố *hợp đồng*, còn lời giải thích ở giữa thân phương thức dùng để bảo tồn *lý do thiết kế* khó nhận thấy.

## 2. Ba dạng chú thích Java

Java hỗ trợ các cú pháp chính:

| Loại | Cú pháp | Dùng khi |
| --- | --- | --- |
| Một dòng | `// nội dung` | Giải thích ngắn ngay trước một quyết định |
| Nhiều dòng | `/* nội dung */` | Ghi chú ngắn nhiều dòng; tránh dài và lặp mã |
| Javadoc | `/** nội dung */` | Viết tài liệu có cấu trúc cho lớp, phương thức, constructor hoặc thành viên thích hợp |

Ví dụ **minh họa bên trong phương thức**, chưa phải file có `main`:

```java
// Phần dư chưa đủ một bậc tích điểm không được quy đổi.
long basePoints = amountVnd / 10_000L;

/*
 * Với hợp đồng này, kết quả được giới hạn theo ngưỡng
 * đã được quyết định trước trong chính sách sản phẩm.
 */
long limitedPoints = Math.min(basePoints, 500L);
```

Trình biên dịch bỏ qua nội dung chú thích `//` và `/* ... */` khi phân tích chương trình. Tuy nhiên, trình tạo tài liệu **`javadoc`** có thể đọc các khối `/** ... */` và sinh tài liệu HTML.

Không đặt `//` trong chuỗi `"https://example.org"` rồi nghĩ nó sẽ bắt đầu chú thích: trong string literal, dấu `//` chỉ là ký tự văn bản. Không lồng `/* ... */` vào bên trong một `/* ... */` khác vì Java không hỗ trợ block comment lồng nhau.

## 3. Chú thích “vì sao”, không lặp “làm gì”

### Chú thích thừa

```java
count++;               // Tăng count lên một.
price = price * 2;     // Nhân giá với hai.
return price;          // Trả về price.
```

Các câu sau `//` chỉ diễn giải đúng cú pháp mà người đọc đã nhìn thấy. Nếu mọi dòng đều có chú thích như vậy, việc rà soát mã chậm hơn mà không tăng hiểu biết.

### Chú thích giữ lại lý do có giá trị

```java
// Chỉ tính điểm cho mỗi bậc 10.000 VND tròn;
// làm tròn lên sẽ cấp điểm cho cả phần tiền chưa đủ bậc.
long basePoints = amountVnd / 10_000L;
```

Ở đây, một phép chia nguyên có thể nhìn giống “vô tình làm mất phần thập phân”. Chú thích giải thích vì sao **phải** chia nguyên: đó là chính sách tính điểm, không phải lỗi làm tròn.

Một ví dụ khác:

```java
// Khoảng [start, end) tránh tính hai lần mốc chung
// khi ghép hai ca liên tiếp [9:00, 10:00) và [10:00, 11:00).
return minute >= startInclusive && minute < endExclusive;
```

Người đọc thấy ngay ý nghĩa biểu thức nhưng khó biết lý do dùng `< endExclusive` thay cho `<= endExclusive`. Chú thích lưu lại quyết định thiết kế để người sửa không vô tình tạo lỗi tại ranh giới.

**Kiểm tra chất lượng chú thích:** Nếu xóa chú thích mà người đọc vẫn hiểu đủ lý do từ tên hàm và biểu thức, có lẽ chú thích đó không cần thiết. Nếu thiếu chú thích khiến họ dễ sửa sai một quy tắc quan trọng, chú thích nên được giữ.

## 4. Javadoc là hợp đồng của phương thức

Javadoc bắt đầu bằng `/**`, đặt **ngay trước khai báo** muốn mô tả. Thông thường tài liệu phương thức gồm một câu mô tả ngắn, sau đó giải thích ràng buộc quan trọng, và các thẻ dành cho người gọi.

```java
/**
 * Tính điểm tích lũy theo giá trị đơn hàng.
 *
 * <p>Mỗi 10.000 VND tròn được một điểm cơ bản. Thành viên
 * nhận điểm gấp đôi khi đơn hàng đạt ít nhất 100.000 VND.
 * Kết quả không vượt 500 điểm.
 *
 * @param amountVnd giá trị đơn hàng tính bằng VND, không âm
 * @param member true nếu khách hàng là thành viên
 * @return số điểm được cấp, từ 0 đến 500
 * @throws IllegalArgumentException nếu amountVnd âm
 */
public static int calculatePoints(long amountVnd, boolean member) {
    // Phần thân phương thức được trình bày đầy đủ ở ví dụ bên dưới.
    return 0;
}
```

Đoạn trên **chỉ minh họa cấu trúc Javadoc**, phần thân trả `0` là mã minh họa hình dạng phương thức, chưa phải hiện thực của chính sách đã mô tả. Dùng phiên bản hoàn chỉnh ở phần 5 để biên dịch và chạy. Không đưa một phần thân giả như vậy vào mã sản phẩm.

Các thẻ hay dùng:

| Thẻ | Nội dung nên viết | Khi dùng |
| --- | --- | --- |
| Mô tả đầu `/** ... */` | Phương thức có ý nghĩa gì, điều kiện chính của hợp đồng | Khi phương thức cần tài liệu |
| `@param name` | Ý nghĩa, đơn vị, giới hạn của từng tham số | Khi tài liệu hóa tham số |
| `@return` | Ý nghĩa giá trị trả về, giới hạn, sentinel nếu có | Với phương thức có giá trị trả về |
| `@throws ExceptionType` | Loại ngoại lệ và điều kiện làm phát sinh | Khi caller cần biết điều kiện lỗi |
| `@see Type#method(...)` | Dẫn tới API liên quan | Khi liên kết bổ sung có ích |
| `@since` | Phiên bản API bắt đầu xuất hiện | Với API có quản lý phiên bản |
| `@deprecated` | Giải thích API cũ và lối thay thế | Khi API được ngừng khuyến nghị |

**Phân biệt `@throws` và `throws`:** `@throws` là **thẻ tài liệu** viết trong comment; `throws IOException` là **cú pháp Java** trong chữ ký để khai báo khả năng phát sinh checked exception. Viết `@throws IOException` không thay được phần `throws IOException` mà compiler yêu cầu.

Các `@param` phải khớp tên tham số thật. Nếu đổi `amountVnd` thành `orderValue`, cần sửa lại tên trong tài liệu. Với JavaDoc, các ký tự trông như HTML cần được viết cẩn thận: ưu tiên `{@code >=}`, `{@code <}` hoặc `&lt;` trong văn bản Javadoc để tránh lỗi phân tích markup. `{@code ...}` thường thích hợp để nhắc tới đoạn mã ngắn.

## 5. Chương trình Java 17+ đầy đủ: chính sách tích điểm

Tạo file **`LoyaltyPolicy.java`**:

```java
/**
 * Quy tắc tích điểm cho đơn hàng, dùng đơn vị tiền là VND.
 */
public final class LoyaltyPolicy {
    private LoyaltyPolicy() {
        // Không tạo đối tượng từ lớp tiện ích.
    }

    /**
     * Tính số điểm tích lũy được cấp cho một đơn hàng.
     *
     * <p>Mỗi 10.000 VND tròn mang lại một điểm cơ bản.
     * Thành viên nhận điểm gấp đôi từ mức 100.000 VND.
     * Tổng điểm tối đa cho một đơn là 500.
     *
     * @param amountVnd tổng tiền đơn hàng, đơn vị VND, phải không âm
     * @param member true nếu người mua là thành viên
     * @return số điểm của đơn hàng trong khoảng 0 đến 500
     * @throws IllegalArgumentException nếu amountVnd âm
     */
    public static int calculatePoints(long amountVnd, boolean member) {
        if (amountVnd < 0) {
            throw new IllegalArgumentException(
                    "amountVnd must be non-negative");
        }

        // Phần dư dưới 10.000 VND chưa đủ một bậc tích điểm.
        long basePoints = amountVnd / 10_000L;

        long awarded = member && amountVnd >= 100_000L
                ? basePoints * 2
                : basePoints;

        // Giữ trần để đơn giá trị lớn không được cấp điểm vô hạn.
        return (int) Math.min(awarded, 500L);
    }
}
```

Tạo file **`LoyaltyDemo.java`** cùng thư mục:

```java
public class LoyaltyDemo {
    public static void main(String[] args) {
        System.out.println("regular="
                + LoyaltyPolicy.calculatePoints(45_000L, false));
        System.out.println("member="
                + LoyaltyPolicy.calculatePoints(120_000L, true));
        System.out.println("capped="
                + LoyaltyPolicy.calculatePoints(3_000_000L, true));

        try {
            LoyaltyPolicy.calculatePoints(-1L, true);
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
```

Chạy tại thư mục chứa hai file, bằng **JDK 17+** (PowerShell, CMD hoặc bash). Tạo thư mục `out` nếu chưa có:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out LoyaltyPolicy.java LoyaltyDemo.java
java -cp out LoyaltyDemo
```

**Stdout chính xác:**

```text
regular=4
member=24
capped=500
error=amountVnd must be non-negative
```

Đối chiếu với hợp đồng và chú thích:

- `45_000 / 10_000` cho `4` bậc nguyên; người mua thường nhận 4 điểm.
- `120_000 / 10_000` cho 12 điểm cơ bản; thành viên đạt ngưỡng 100.000 VND nhận 24 điểm.
- `3_000_000 / 10_000` cho 300 điểm cơ bản; nhân đôi thành 600 nhưng giới hạn 500.
- Giá trị âm bị từ chối bằng `IllegalArgumentException` đúng như thẻ `@throws`.

Phương thức `calculatePoints` **không cần khai báo `throws IllegalArgumentException`**, bởi đó là unchecked exception; thông tin ở `@throws` vẫn hữu ích vì caller biết điều kiện sai. Dùng `long` cho số tiền giúp tránh sự thiếu hụt miền giá trị của `int` trong ví dụ; phép nhân đôi ở đây không tràn `long` vì kết quả của phép chia `amountVnd / 10_000L` được chặn bởi miền của `long`.

Trong ví dụ có hai cấp tài liệu: **Javadoc** mô tả hợp đồng bên ngoài của phương thức; **chú thích trong thân** diễn giải lý do làm tròn xuống và lý do đặt trần. Không cần thêm các câu như `// kiểm tra nếu amountVnd nhỏ hơn 0` vì biểu thức `if` đã nói rõ điều đó.

## 6. Sinh tài liệu HTML từ Javadoc

Khi chương trình đã có một API cần người khác đọc, công cụ **`javadoc`** đi kèm JDK có thể tạo trang HTML từ các khối `/** ... */`:

```sh
javadoc -encoding UTF-8 -docencoding UTF-8 -d docs LoyaltyPolicy.java
```

Tùy hệ điều hành, shell và JDK, thông báo tiến trình của lệnh `javadoc` sẽ khác nhau; không có stdout cố định cần ghi nhớ. Sau khi chạy thành công, xem trang tài liệu tương ứng của `LoyaltyPolicy` trong thư mục `docs` (ví dụ `docs/LoyaltyPolicy.html`).

`-encoding UTF-8` áp dụng khi đọc source; `-docencoding UTF-8` chỉ định encoding của tài liệu được tạo. `javac` vẫn chịu trách nhiệm biên dịch mã, còn `javadoc` tạo tài liệu cho người đọc. Tài liệu HTML không bảo đảm logic đúng và không thay thế kiểm thử.

Có thể dùng `javadoc -Xdoclint:all ...` trong môi trường hỗ trợ để kiểm tra thêm nội dung và cấu trúc Javadoc. Đây là bước kiểm tra chất lượng tài liệu, không phải lời hứa rằng mọi điều kiện nghiệp vụ đã được thực thi đúng.

## 7. Tình huống cần giải thích lý do: khoảng thời gian nửa mở

Đối với bài toán ghép ca làm việc liên tiếp, dùng khoảng `[startInclusive, endExclusive)` rất hữu ích: mốc kết thúc của ca trước sẽ là mốc bắt đầu của ca tiếp theo, nhưng không bị tính vào cả hai ca.

Tạo file **`TimeWindowDemo.java`**:

```java
public class TimeWindowDemo {
    /**
     * Kiểm tra một phút có thuộc khoảng thời gian nửa mở hay không.
     *
     * <p>Khoảng có dạng [startInclusive, endExclusive), nghĩa là
     * phút đầu được tính nhưng phút cuối không được tính.
     *
     * @param minute phút cần kiểm tra, tính từ đầu ngày
     * @param startInclusive phút đầu được tính
     * @param endExclusive phút cuối không được tính
     * @return true nếu minute thuộc khoảng
     */
    static boolean contains(int minute, int startInclusive, int endExclusive) {
        // Loại trừ mốc cuối giúp hai ca giáp nhau không tính trùng.
        return minute >= startInclusive && minute < endExclusive;
    }

    public static void main(String[] args) {
        System.out.println("09:59=" + contains(599, 540, 600));
        System.out.println("10:00-before=" + contains(600, 540, 600));
        System.out.println("10:00-next=" + contains(600, 600, 660));
    }
}
```

Ở đây số phút tính từ đầu ngày: 09:00 là 540, 09:59 là 599, 10:00 là 600.

```sh
javac -encoding UTF-8 --release 17 -d out TimeWindowDemo.java
java -cp out TimeWindowDemo
```

Stdout:

```text
09:59=true
10:00-before=false
10:00-next=true
```

Chú thích có giá trị vì giúp người sửa hiểu lý do của `minute < endExclusive`. Chữ ký có tên `startInclusive`/`endExclusive` làm rõ phần “làm gì”; Javadoc bổ sung đơn vị đo và ý nghĩa kết quả.

**Giới hạn của ví dụ:** phương thức giả định các phút được truyền hợp lệ (`0`–`1439` cho `minute`; ranh giới hợp lý trong ngày cho `startInclusive` và `endExclusive`, `startInclusive <= endExclusive`). Nó chưa kiểm tra dữ liệu đầu vào. Nếu chuyển thành public API nhận dữ liệu người dùng, cần thiết kế và thực thi validation, đồng thời tài liệu hóa quy tắc lỗi; chỉ viết `@param` không tự kiểm tra giới hạn.

## 8. Khi nào cần Javadoc và khi nào có thể bỏ?

| Trường hợp | Gợi ý |
| --- | --- |
| Public API dùng bởi lớp/module/người khác | Tài liệu hóa mục đích, đơn vị, điều kiện, output, ngoại lệ và tác dụng phụ quan trọng |
| Phương thức có quy tắc nghiệp vụ khó đoán | Mô tả hợp đồng với Javadoc; ghi chú lý do ngay bên cạnh quyết định bất ngờ |
| Internal helper ngắn, tên và kiểu tự nói lên hành vi | Có thể bỏ chú thích để giảm nhiễu |
| Phương thức phức tạp có giả định hoặc thuật toán ít gặp | Ghi rõ bất biến, tiền/hậu điều kiện, lý do chọn hướng tiếp cận; thêm ví dụ khi cần |
| Override thực hiện đúng hợp đồng đã rõ ở cha/interface | Tránh sao chép tài liệu; có thể dùng `{@inheritDoc}` nếu phù hợp |
| API có tác dụng phụ, thay đổi trạng thái hay luồng thực thi | Nêu hành vi quan trọng để caller không sử dụng sai |
| API cũ đang bị thay thế | Ghi `@Deprecated` trong Java và Javadoc `@deprecated` kèm hướng chuyển đổi |
| Thử nghiệm một lần rất ngắn, tên biến rõ | Không cần viết tài liệu dài cho từng dòng |

Mục tiêu không phải đạt số dòng comment hay phần trăm bao phủ Javadoc cao nhất. Mục tiêu là người đọc **dự đoán được hợp đồng** và **không xóa mất quyết định thiết kế quan trọng** chỉ vì mã nhìn có vẻ có thể đơn giản hơn.

## 9. Viết Javadoc tốt: những điều nên nói rõ

Đối với phương thức cần tài liệu, hãy rà từng nhóm thông tin sau nếu chúng có ý nghĩa:

1. **Ý nghĩa kết quả:** ví dụ “điểm tích lũy”, không chỉ “trả về `int`” vì chữ ký đã nói kiểu.
2. **Đơn vị:** `amountVnd` là VND, `durationSeconds` là giây; không nên để người dùng tự suy ra.
3. **Miền hợp lệ:** số âm bị từ chối, `null` có được không, danh sách rỗng xử lý thế nào.
4. **Ranh giới:** khoảng đóng `[a,b]` hay nửa mở `[a,b)`, các ngưỡng `>=` và `>` khác nhau ra sao.
5. **Điều kiện lỗi:** chính xác loại ngoại lệ và tình huống xảy ra. `@throws` mô tả hành vi thực tế; không liệt kê bừa mọi ngoại lệ của Java.
6. **Tác dụng phụ:** cập nhật trạng thái, gọi I/O, sửa mutable argument, đóng tài nguyên, tác động đến thứ tự xử lý.
7. **Độ xác định:** cùng input cho cùng output không, có phụ thuộc giờ hiện tại, locale, cấu hình hay nguồn dữ liệu ngoài không.
8. **Quy tắc làm tròn hoặc sentinel:** ví dụ chia nguyên bỏ phần dư, `-1` biểu thị không tìm thấy, `Optional.empty()` biểu thị không có giá trị, nếu có.

Viết theo nhu cầu của caller. Javadoc của `calculatePoints` không cần tường thuật “khai báo biến `basePoints` rồi gọi `Math.min`”; đó là chi tiết triển khai mà người gọi không cần biết và có thể thay đổi.

## 10. Những lỗi chú thích và Javadoc thường gặp

**Chú thích lỗi thời.** Ví dụ:

```java
// Giảm giá 10%.
int discounted = price * 80 / 100;
```

Mã hiện đang giảm 20%, còn chú thích nói 10%. Khi thay đổi quy tắc, cần cập nhật cả mã, test và tài liệu; tốt hơn là đặt tên hằng như `DISCOUNT_PERCENT` để tránh nhiều nơi nêu lại giá trị.

**Chú thích mơ hồ:** `// fix bug`, `// logic khó`, `// xử lý đặc biệt` không giúp người khác. Nên giải thích điều kiện cụ thể và hệ quả nếu bỏ quyết định đó. Không dùng chú thích để giữ lại một khối mã cũ bị vô hiệu hóa; lịch sử Git phù hợp hơn.

**Javadoc trái với hành vi:** ghi `@return null if missing` trong khi mã ném ngoại lệ, hoặc ghi `@throws IOException` nhưng thực tế không có đường thực thi nào ném loại đó theo hợp đồng, gây hiểu lầm. Viết tài liệu sau khi đã thống nhất hành vi và kiểm tra lại sau sửa đổi.

**Lặp nghĩa của tên:** `/** Gets customer. */ Customer getCustomer()` hầu như không thêm thông tin. Nếu getter chỉ trả trường tương ứng, API nội bộ đơn giản có thể không cần giải thích riêng; nếu trả bản sao phòng vệ hoặc đọc dữ liệu từ xa thì nên nói rõ điều đó.

**Sai tên thẻ:** `@param amount` khi phương thức khai báo `amountVnd`; hoặc `@return` cho phương thức `void`. Chạy `javadoc`/doclint để phát hiện một số vấn đề cấu trúc.

**Lẫn Javadoc với chú thích bình thường:** `// @param value ...` không tạo thẻ `@param` trong tài liệu sinh ra; thẻ cần nằm trong khối Javadoc. Mã Java vẫn biên dịch nếu chú thích chưa hoàn chỉnh, nhưng tài liệu cho caller không vì thế mà tự đúng.

**Nhúng ký hiệu markup sai:** trong Javadoc, dấu `<`, `>`, `&` có thể liên quan cú pháp HTML. Dùng `{@code ...}` hoặc escape phù hợp khi muốn hiển thị mã và toán tử. Đừng đặt ví dụ Java nhiều dòng tùy tiện trong HTML khiến trang tài liệu bị vỡ; dùng cấu trúc hỗ trợ và kiểm tra trang kết quả.

**Viết quá dài cho hàm quá nhỏ:** nội dung thừa khó đồng bộ. Nếu một tên hàm rõ nghĩa cùng kiểu dữ liệu đủ truyền đạt hợp đồng, vài câu giải thích trọng yếu sẽ tốt hơn một trang lặp lại mã.

## 11. Quy trình bảo trì chú thích cùng mã

Khi thay đổi phương thức:

1. Đọc tên, chữ ký, Javadoc và các comment gần vùng mã cần sửa; xác định **hợp đồng hiện tại**.
2. Thay đổi code và kiểm thử theo yêu cầu; giữ rõ cái gì thay đổi ở đầu vào, tính toán, kết quả, ngoại lệ.
3. Cập nhật mô tả, các thẻ `@param`/`@return`/`@throws`, ngưỡng/đơn vị và comment “vì sao” nếu quyết định đã đổi.
4. Loại bỏ chú thích thừa hoặc lỗi thời; đừng để comment mâu thuẫn với biểu thức.
5. Chạy `javac`, kiểm tra stdout/test và sinh `javadoc` khi API/tài liệu liên quan bị sửa.
6. Nhờ người đọc khác nhìn tài liệu **trước khi xem phần thân**: họ có dự đoán đúng kết quả và lỗi không?

Một review tốt không chỉ hỏi “comment đã có chưa” mà hỏi “comment còn đúng không, và có giải thích lý do mà tên/mã chưa thể hiện không?”.

## 12. Tự kiểm tra

**1. Chú thích `// tăng i lên một` sau `i++` có cần không?** Thường không; nó lặp đúng thao tác đã hiển thị.

**2. Vì sao nên ghi chú khi dùng khoảng `[start, end)`?** Để giải thích tránh đếm trùng mốc chung giữa các khoảng liên tiếp, chứ không phải chỉ nhắc `<` nghĩa là “nhỏ hơn”.

**3. Nếu phương thức có tham số `amountVnd` nhưng Javadoc ghi `@param amount`, lỗi gì?** Tên trong tài liệu không khớp chữ ký; cập nhật thẻ, dùng `javadoc`/doclint để rà soát.

**4. `@throws IllegalArgumentException` có tự ném ngoại lệ khi số âm không?** Không. Nó chỉ mô tả hợp đồng; nhánh `throw new IllegalArgumentException(...)` trong mã mới thực sự báo lỗi.

**5. Khi API thay đổi ngưỡng từ 100.000 lên 200.000 VND, cần sửa gì?** Quy tắc ở mã, các bài test và mọi Javadoc/chú thích mô tả ngưỡng. Nếu không, tài liệu sẽ gây hiểu lầm.

**6. `javac` có tự sinh trang HTML từ `/** ... */` không?** Không. Công cụ `javadoc` được dùng để sinh tài liệu, còn `javac` biên dịch chương trình.

**Ghi nhớ:** Hãy để tên và cấu trúc mã giải thích *làm gì*; comment nên lưu lại *vì sao*, còn Javadoc nên cho người gọi biết *hợp đồng* — dữ liệu hợp lệ, kết quả, ngoại lệ và giới hạn. Viết khi có giá trị, rồi duy trì cùng mỗi lần thay đổi hành vi.
