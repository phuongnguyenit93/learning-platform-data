# `String.substring()`: biên đầu bao gồm, biên cuối không bao gồm trong Java

Phương thức `substring()` dùng để **trích xuất một phần văn bản** từ `String`. Quy tắc trọng tâm của overload hai tham số là: **lấy ký tự từ vị trí `beginIndex` (bao gồm) đến ngay trước vị trí `endIndex` (không bao gồm)**.

```java
String text = "ABCDE";
String part = text.substring(1, 4); // "BCD"
```

Chỉ số của `String` bắt đầu từ **0**. Trong `"ABCDE"`, các chỉ số 1, 2, 3 lần lượt ứng với `B`, `C`, `D`; vị trí 4 (`E`) là biên kết thúc và **không nằm trong kết quả**. Có thể mô tả khoảng bằng ký hiệu nửa mở **`[beginIndex, endIndex)`**.

Đây là quy tắc nền tảng để cắt chuỗi đúng, tránh lỗi lệch một vị trí (*off-by-one*) và tránh ngoại lệ khi xử lý dữ liệu.

## 1. Hai overload của `substring()`

| API | Phạm vi được lấy | Ví dụ với `"ABCDE"` |
| --- | --- | --- |
| `substring(int beginIndex)` | Từ `beginIndex` (bao gồm) **đến hết chuỗi** | `substring(2)` → `"CDE"` |
| `substring(int beginIndex, int endIndex)` | Từ `beginIndex` (bao gồm) tới **trước** `endIndex` | `substring(1, 4)` → `"BCD"` |

`substring(beginIndex)` tương đương **về nội dung** với `substring(beginIndex, text.length())`. Cả hai trả về một `String`; `String` gốc không bị sửa vì `String` trong Java là **bất biến** (*immutable*).

### Hình dung chỉ số

```text
Ký tự:       A    B    C    D    E
Vị trí:      0    1    2    3    4    5
             |----|----|----|----|----|
substring(1, 4)
                  B    C    D
             [    1 ------------ 4    )
```

Đối với `"ABCDE"`, `length() == 5`. Chỉ số **5** là vị trí ngay **sau** ký tự cuối, hoàn toàn hợp lệ với vai trò **biên cuối**; nó không phải chỉ số của một ký tự có thể gọi `charAt(5)`.

## 2. Quy tắc chính xác cho khoảng `[beginIndex, endIndex)`

Với chuỗi `s` có `n = s.length()`, hai chỉ số của overload hai tham số phải thỏa:

```text
0 <= beginIndex <= endIndex <= n
```

- **Biên đầu bao gồm:** ký tự tại vị trí `beginIndex` được lấy, miễn là khoảng không rỗng.
- **Biên cuối không bao gồm:** ký tự tại vị trí `endIndex` không được lấy.
- **Độ dài kết quả:** luôn bằng `endIndex - beginIndex`, tính theo **UTF-16 code unit**.
- **Hai biên bằng nhau:** `substring(k, k)` trả về chuỗi rỗng `""` đối với mọi `k` trong khoảng `0..n`.
- **Lấy toàn bộ:** `substring(0, n)` có cùng nội dung với `s`.
- **Lấy đến hết:** `substring(k, n)` hoặc `substring(k)`.
- **Lấy một code unit ở vị trí `i`:** `substring(i, i + 1)` nếu `0 <= i < n`.

Với overload một tham số, điều kiện là **`0 <= beginIndex <= n`**. Vì thế `s.substring(s.length())` hợp lệ và trả về chuỗi rỗng; `s.substring(s.length() + 1)` không hợp lệ.

### Vì sao thiết kế biên cuối không bao gồm lại tiện?

Quy tắc nửa mở giúp làm việc với chỉ số mà không phải cộng hoặc trừ 1 trong nhiều tình huống:

- **Đếm đơn vị trong đoạn:** `end - begin`.
- **Đoạn rỗng:** `begin == end`.
- **Chia liền kề:** `s.substring(0, k)` và `s.substring(k, s.length())` bao phủ cả chuỗi, không trùng và không mất code unit.
- **Cắt phần cuối:** không cần đoán chỉ số ký tự cuối; dùng `s.length()` làm biên cuối.
- **Lặp theo khoảng:** tương ứng quy tắc thường gặp `for (int i = begin; i < end; i++)`.

Ví dụ, `"ABCDE".substring(0, 2)` lấy `"AB"` và `"ABCDE".substring(2, 5)` lấy `"CDE"`. Điểm cắt **2** là đầu của đoạn sau và cuối loại trừ của đoạn trước.

## 3. Ví dụ Java 17+ chạy độc lập

Lưu nội dung sau vào `SubstringBasics.java`:

```java
public class SubstringBasics {
    public static void main(String[] args) {
        String text = "ABCDE";

        System.out.println(text.substring(1, 4));
        System.out.println(text.substring(0, 1));
        System.out.println(text.substring(4, 5));

        System.out.println(text.substring(2, 2).isEmpty());
        System.out.println(text.substring(text.length()).isEmpty());

        System.out.println(text.substring(2));
        System.out.println(text.equals("ABCDE"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SubstringBasics.java
java SubstringBasics
```

Kết quả chính xác:

```text
BCD
A
E
true
true
CDE
true
```

Giải thích:

1. `substring(1, 4)` lấy `B`, `C`, `D`, **không** lấy `E`.
2. `substring(0, 1)` lấy đúng phần tử tại chỉ số 0.
3. `substring(4, 5)` lấy đúng phần tử tại chỉ số 4, cũng là code unit cuối.
4. `substring(2, 2)` lấy đoạn dài 0 nên `isEmpty()` là `true`.
5. `substring(text.length())` bắt đầu ngay sau phần tử cuối, cũng trả về chuỗi rỗng.
6. `substring(2)` lấy toàn bộ phần còn lại (`CDE`).
7. `text` gốc vẫn là `"ABCDE"`; `substring()` không xóa, di chuyển hoặc chỉnh sửa ký tự trong `text`.

## 4. Lỗi chỉ số và ngoại lệ

Khi các biên nằm ngoài điều kiện hợp lệ, `substring()` ném `IndexOutOfBoundsException`; trong OpenJDK, bạn thường nhìn thấy lớp cụ thể `StringIndexOutOfBoundsException`. Thông điệp ngoại lệ có thể khác giữa các JDK, nên ứng dụng không nên phụ thuộc vào đúng câu thông báo.

Ví dụ các lời gọi **không hợp lệ** với `"ABCDE"`:

| Lời gọi | Nguyên nhân |
| --- | --- |
| `substring(-1, 2)` | `beginIndex` âm |
| `substring(2, 6)` | `endIndex` lớn hơn `length() == 5` |
| `substring(4, 3)` | `beginIndex > endIndex` |
| `substring(6)` | Biên đầu lớn hơn độ dài |
| `substring(0, -1)` | Biên cuối âm |

Một đoạn rỗng **không phải lỗi** khi hai biên bằng nhau và trong phạm vi hợp lệ: `substring(5, 5)` là hợp lệ với chuỗi dài 5. Tương tự, `substring(0, 0)` cũng trả về chuỗi rỗng.

### Kiểm tra trước khi cắt

Khi các chỉ số do người dùng hoặc API khác cung cấp, hãy xác minh trước:

```java
public static String slice(String text, int begin, int end) {
    if (text == null) {
        throw new IllegalArgumentException("text must not be null");
    }
    if (begin < 0 || end < begin || end > text.length()) {
        throw new IllegalArgumentException("invalid substring bounds");
    }
    return text.substring(begin, end);
}
```

Đây là một **phương thức minh họa** cần đặt trong một class; nó không phải chương trình `main` độc lập. Nếu `text` là `null`, gọi trực tiếp `text.substring(...)` sẽ gây `NullPointerException`; vì thế kiểm tra `null` là trách nhiệm tách biệt với kiểm tra phạm vi.

Có hai chính sách xử lý thường dùng:

- **Từ chối biên sai:** ném ngoại lệ rõ nghĩa khi API yêu cầu đoạn phải chính xác.
- **Giới hạn trong phạm vi hợp lệ:** chỉ thực hiện khi nghiệp vụ chấp nhận cắt ngắn, ví dụ lấy preview tối đa ba code unit bằng `text.substring(0, Math.min(3, text.length()))` trên chuỗi không `null`.

Không nên âm thầm dùng `Math.min` để chữa mọi `endIndex` sai, vì lỗi lập trình có thể bị che khuất và dữ liệu trả về có thể khác mong muốn.

## 5. Ứng dụng: trích xuất các trường có độ rộng cố định

Khoảng nửa mở đặc biệt hữu ích khi dữ liệu quy định **vị trí đầu và số code unit** cần lấy. Nếu một trường bắt đầu tại `start` và có `count` code unit, biên cuối là `start + count`. Trước khi cộng, hãy kiểm tra `count <= text.length() - start` để tránh vượt biên hay tràn số nguyên.

Ví dụ, chuỗi `"20261023ACTIVE"` chứa ngày tám chữ số theo sau bởi trạng thái sáu chữ cái. Lưu thành `FixedFieldSliceDemo.java`:

```java
public class FixedFieldSliceDemo {
    static String field(String text, int start, int count) {
        if (start < 0 || start > text.length()
                || count < 0 || count > text.length() - start) {
            throw new IndexOutOfBoundsException("Invalid fixed-width field");
        }
        return text.substring(start, start + count);
    }

    public static void main(String[] args) {
        String record = "20261023ACTIVE";
        System.out.println("date=" + field(record, 0, 8));
        System.out.println("status=" + field(record, 8, 6));
        System.out.println("empty=" + field(record, record.length(), 0).isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 FixedFieldSliceDemo.java
java FixedFieldSliceDemo
```

```text
date=20261023
status=ACTIVE
empty=true
```

Ví dụ này minh họa trực tiếp công thức `end = start + count` và lý do biên cuối loại trừ. Khi trường được định nghĩa theo **ký tự Unicode** hoặc grapheme thay vì code unit, phải chuyển đổi ranh giới trước khi gọi `substring`.

## 6. Lưu ý quan trọng: chỉ số của `substring()` là UTF-16

`length()` và hai biên của `substring` tính theo **UTF-16 code unit**. Emoji ngoài BMP thường chiếm hai code unit; vì vậy `"A😀B".length() == 4` dù chuỗi có ba code point. Cắt `substring(1, 3)` lấy trọn emoji, còn `substring(1, 2)` chỉ giữ high surrogate.

Nếu yêu cầu là cắt theo code point, hãy tìm biên bằng `offsetByCodePoints` rồi mới truyền kết quả vào `substring`. Nếu phải giữ cả dấu kết hợp hoặc emoji nhiều code point, cần ranh giới grapheme; kiểm tra số học `0 <= begin <= end <= length` chỉ bảo vệ offset chứ không bảo đảm cụm hiển thị không bị tách.

## 7. Các sai lầm phổ biến

1. **Tưởng biên cuối được lấy:** `"ABCDE".substring(1, 4)` là `"BCD"`, không phải `"BCDE"`.
2. **Lấy nhầm một ký tự:** muốn lấy code unit tại index `i` bằng `substring(i, i + 1)`, không phải `substring(i, i)` (chuỗi rỗng). Với Unicode cần cân nhắc code point/grapheme.
3. **Tự trừ 1 khi lấy hết chuỗi:** `substring(0, length() - 1)` sẽ **bỏ ký tự cuối**. Muốn lấy toàn bộ thì dùng `substring(0, length())`.
4. **Nghĩ `endIndex == length()` là sai:** đây là trường hợp hợp lệ và rất thông dụng.
5. **Nhầm số lượng ký tự với chỉ số cuối:** để lấy `count` code unit từ `start`, biên cuối là `start + count` (chỉ khi còn nằm trong phạm vi). Chẳng hạn lấy ba code unit từ chỉ số 2 thì dùng `substring(2, 5)`, không dùng `substring(2, 3)`.
6. **Quên kiểm tra `indexOf() == -1`:** nếu dấu phân cách không tồn tại, dùng `-1` làm chỉ số cắt dễ dẫn tới lỗi.
7. **Nhầm `substring()` với `split()`:** `split()` sử dụng regex và trả về mảng chuỗi; `substring()` dùng biên vị trí và trả về một chuỗi. Muốn tách theo một dấu đơn giản thường có thể kết hợp `indexOf` và `substring`.
8. **Nghĩ `substring()` sửa chuỗi gốc:** `String` bất biến; kết quả trả về được gán cho biến mới hoặc gán lại biến hiện có, không làm nội dung đối tượng `String` gốc thay đổi.
9. **Dùng `substring()` với chỉ số do người dùng nhập nhưng không kiểm tra biên:** các giá trị âm, đảo thứ tự hoặc vượt `length()` đều có thể gây ngoại lệ.
10. **Cắt chuỗi Unicode ở ranh giới code unit:** có thể phá cặp surrogate hoặc cụm ký tự người dùng nhận thấy. Chọn đơn vị đếm dựa trên yêu cầu.

## 8. Bài tập kiểm tra nhanh

Giả sử `s = "ABCDEFG"` (`length() == 7`). Hãy tự dự đoán kết quả trước khi đọc đáp án.

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `s.substring(0, 3)` | `"ABC"` | Bao gồm 0, 1, 2; không lấy 3 |
| `s.substring(3, 7)` | `"DEFG"` | Lấy từ D đến hết, biên 7 hợp lệ |
| `s.substring(3)` | `"DEFG"` | Overload một tham số lấy phần đuôi |
| `s.substring(0, 0)` | `""` | Biên bằng nhau cho đoạn rỗng |
| `s.substring(7, 7)` | `""` | Đoạn rỗng ở cuối chuỗi |
| `s.substring(3, 2)` | Ngoại lệ | Biên đầu lớn hơn biên cuối |
| `s.substring(0, 8)` | Ngoại lệ | Biên cuối vượt độ dài 7 |

Đặc biệt, `s.substring(0, 3).length()` bằng **3**, đúng bằng `3 - 0`. Nếu trích hai đoạn `left = s.substring(0, 3)` và `right = s.substring(3, s.length())` thì `left + right` có cùng nội dung với `s`.

## 9. Checklist khi sử dụng `substring()`

1. Xác định đoạn cần lấy theo **chỉ số UTF-16** hay theo code point/grapheme của Unicode.
2. Chọn hai mốc `begin` và `end`; nhớ rằng **đầu lấy, cuối không lấy**.
3. Kiểm tra `0 <= begin <= end <= text.length()`.
4. Dùng `substring(begin, end)` cho đoạn giới hạn hai đầu hoặc `substring(begin)` cho phần còn lại.
5. Nếu biên tính từ dấu phân cách, kiểm tra kết quả `indexOf`/`lastIndexOf` trước khi sử dụng.
6. Thử các trường hợp mép: chuỗi rỗng, `begin == end`, `end == length()`, không tìm thấy dấu mốc và Unicode nhiều code unit.

**Ghi nhớ:** `substring(beginIndex, endIndex)` lấy khoảng **`[beginIndex, endIndex)`**. Biên đầu **bao gồm**, biên cuối **không bao gồm**, nên độ dài đoạn luôn là **`endIndex - beginIndex`** theo đơn vị UTF-16 của `String`.
