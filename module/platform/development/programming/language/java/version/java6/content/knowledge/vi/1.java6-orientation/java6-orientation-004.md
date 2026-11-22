# Đọc Javadoc hiện hành và đối chiếu thông tin Since

## 1. Mục tiêu: biết API làm gì hôm nay và có từ khi nào

Khi học một nhóm kiến thức gắn với Java 6, có hai câu hỏi khác nhau:

1. API này có ý nghĩa và hợp đồng sử dụng như thế nào trên Java hiện đại?
2. Kiểu hoặc phương thức cụ thể này được đưa vào nền tảng từ phiên bản nào?

**Javadoc** giúp trả lời câu thứ nhất bằng phần mô tả, tham số, kết quả, ngoại lệ và các ràng buộc. Mục **Since** hỗ trợ câu thứ hai bằng thông tin phiên bản xuất hiện của phần tử đang được mô tả.

Không nên chỉ đọc một bài giới thiệu cũ rồi dùng nguyên các khuyến nghị cũ. Cũng không nên thấy một phương thức nằm trên trang tài liệu mới rồi cho rằng nó chỉ có ở phiên bản mới.

Ví dụ:

- `String.isEmpty()` vẫn được dùng hiện nay, với `Since: 1.6`.
- `String.isBlank()` cũng nằm trên trang `String` hiện hành, nhưng có `Since: 11`.
- Hai phương thức có ý nghĩa khác nhau, không phải cùng một thao tác chỉ được đổi tên.

Cách học trong bài là **đọc hợp đồng hiện hành trước, rồi ghi nhận mốc xuất hiện đúng cấp độ**. Không cần cài JDK 6 để học những API còn phù hợp trên JDK 17+.

## 2. Xác định đúng trang tài liệu trước khi đọc

Một kết quả tìm kiếm có thể trỏ tới Javadoc của nhiều phiên bản Java, một thư viện ngoài hoặc một bản sao không chính thức. Trước khi kết luận, hãy xác định:

| Thông tin | Vì sao cần biết |
| --- | --- |
| Phiên bản bộ tài liệu | Mô tả hợp đồng của phiên bản đó, không tự đại diện mọi phiên bản |
| Package và tên đầy đủ | Phân biệt kiểu trùng tên |
| Module, nếu có | Xác định nơi API hiện được cung cấp trong nền tảng module |
| Chủ sở hữu API | API Java SE/JDK và API thư viện ngoài có hệ phiên bản khác nhau |
| Đúng overload | Các phương thức cùng tên có thể khác tham số, hành vi và mốc xuất hiện |

Ví dụ, `java.lang.String` là tên đầy đủ của lớp cần tra. Trên JDK hiện đại, nó thuộc module `java.base`. Việc nó được đặt trong một module hiện nay không có nghĩa bản thân lớp được tạo ra từ lúc Java có module.

Trong bài, các dẫn chứng Javadoc được đối chiếu với bộ tài liệu Java SE 27/JDK 27. Ví dụ chạy được giới hạn ở các API có sẵn trên JDK 17, để người học không phải dùng mọi API mới thấy trên trang hiện hành.

Nếu dự án thực tế chạy JDK 17 hoặc 21, hãy mở thêm đúng bộ Javadoc của phiên bản đó để xác minh hành vi và bề mặt API được phép sử dụng. “Hiện hành” trong việc duy trì dự án cần bao gồm phiên bản runtime mục tiêu của dự án, không chỉ bộ tài liệu mới nhất trên mạng.

## 3. Đọc từ tổng quan tới hợp đồng phương thức

### 3.1. Đọc phần mô tả kiểu

Trang lớp/interface cho biết vai trò chung, đặc điểm quan trọng và quan hệ kiểu. Ví dụ:

- `String` đại diện chuỗi và có đặc tính không thay đổi nội dung sau khi tạo.
- `NavigableMap` mở rộng cách làm việc với map có thứ tự để tìm khóa gần một giá trị mục tiêu.
- `List` mô tả một danh sách có thứ tự, nhưng không bảo đảm mọi đối tượng List đều cho phép thêm/xóa.

Nếu chỉ nhìn tên phương thức trong bảng tóm tắt, có thể bỏ qua chính những ràng buộc chi phối việc dùng nó.

### 3.2. Dùng Method Summary để tìm, dùng Method Details để quyết định

Bảng tóm tắt giúp định vị nhanh. Sau đó cần mở đúng phần chi tiết để đọc:

1. Chữ ký đầy đủ.
2. Ý nghĩa thao tác.
3. Các tham số và miền giá trị.
4. Giá trị trả về.
5. Ngoại lệ và điều kiện gây ra.
6. Ràng buộc được nêu trong mô tả hoặc liên kết.
7. Mục `Since`, nếu có.

Thứ tự này tránh một cách học thiếu sót: ghi nhớ “có từ Java 6” nhưng vẫn chưa biết lúc nào phương thức trả `null` hoặc có thay đổi dữ liệu gốc hay không.

### 3.3. Đọc đúng overload

Tên phương thức không đủ xác định API cụ thể. Ví dụ, một kiểu có thể có các phương thức:

```java
method(int value)
method(long value)
method(String value)
```

Đây là chữ ký minh họa, không phải khai báo một lớp hoàn chỉnh.

Chúng có thể được bổ sung ở các phiên bản khác nhau. Khi ghi nhận bằng chứng, cần viết đủ tên và kiểu tham số, không chỉ ghi “method có từ phiên bản X”.

Với `List.of`, có nhiều overload theo số phần tử và một overload varargs. Khi đọc lời gọi `List.of("An", "Binh")`, hãy mở đúng overload hai tham số để xem hợp đồng và `Since`.

### 3.4. Theo liên kết Specified by và Overrides khi cần

Một phương thức có thể thực hiện hợp đồng từ interface hoặc ghi đè phương thức ở lớp cha. Liên kết `Specified by`/`Overrides` giúp lần tới nơi mô tả nguồn của hợp đồng.

Đừng cho rằng phương thức xuất hiện trên trang lớp con chắc chắn được khai báo lần đầu ở chính lớp con. Bảng các phương thức kế thừa và các quan hệ này cũng giúp tránh ghi nhầm mốc của kiểu chứa trang thành mốc của mọi thao tác nó hỗ trợ.

## 4. Since có nghĩa gì và không có nghĩa gì?

### 4.1. Đây là thông tin về phần tử cụ thể

Trong tài liệu do standard doclet tạo, mục `Since` thường xuất phát từ thẻ tài liệu `@since`.

Ví dụ mô tả tài liệu minh họa:

```java
/**
 * Tính giá trị theo quy tắc của thư viện.
 *
 * @since 2.3
 */
public int calculate(int value) {
    return value * 2;
}
```

Đây là một đoạn phương thức để minh họa thẻ Javadoc, chưa phải chương trình độc lập.

Nếu đây là thư viện có phiên bản 2.3, `@since 2.3` nói về phiên bản của **thư viện đó**. Không được tự đọc thành Java 2.3.

Với tài liệu nền tảng Java, cách ghi cũ `1.6` tương ứng Java 6; `1.8` tương ứng Java 8. Cần hiểu ngữ cảnh và cách đặt phiên bản của chính bộ tài liệu.

### 4.2. Since ở lớp không áp dụng cho mọi phương thức hiện tại

Một lớp có thể tồn tại lâu trước khi có một phương thức mới. Do đó:

```text
Mốc của lớp
    ≠
mốc của tất cả constructor/phương thức/field hiện thấy trên trang
```

`String` tồn tại trước Java 6, nhưng `String.isEmpty()` được ghi nhận từ 1.6. `String.isBlank()` có mốc 11. Không chọn một mốc ở đầu trang rồi gán cho mọi dòng trong Method Summary.

Quy tắc đọc là xác định đúng phần tử, ưu tiên thông tin ở phần chi tiết của chính phần tử đó.

### 4.3. Không có Since ngay dưới phương thức không phải bằng chứng nó “có từ đầu”

Tài liệu có thể không lặp lại mốc cho mỗi thành viên được đưa vào cùng lúc với kiểu. Đặc tả Javadoc khuyến nghị ghi mốc riêng khi mốc thành viên khác mốc kiểu chứa nó.

Vì vậy, nếu chưa thấy `Since`:

- Kiểm tra đã mở đúng phần chi tiết chưa.
- Kiểm tra kiểu hoặc interface khai báo phương thức.
- Xem thông tin của kiểu chứa và các liên kết kế thừa.
- Nếu cần kết luận lịch sử chính xác, đối chiếu tài liệu phiên bản hoặc bằng chứng API phù hợp.

Không tự tạo ra một số phiên bản chỉ vì mục này không xuất hiện. Đặc biệt, một kiểu có thể được bổ sung supertype mới, kéo theo khả năng có thêm phương thức; việc lớp/interface đã tồn tại lâu không chứng minh nó đã hỗ trợ mọi thao tác hiện tại từ đầu.

### 4.4. Since không phải toàn bộ lịch sử hành vi

Mốc xuất hiện không mô tả mọi lần sửa lỗi, thay đổi diễn giải, cập nhật dữ liệu Unicode hoặc thay đổi chi tiết triển khai của API.

Nếu cần biết hành vi ở JDK 17, không thể chỉ thấy `Since: 1.6` rồi giả định mọi dòng mô tả trong Javadoc 27 là một bản ghi nguyên vẹn từ Java 6.

Cần phân biệt hai kết luận:

- “Phần tử này xuất hiện từ Java 6.”
- “Mọi đặc điểm hiện tại của phần tử này đã được đặc tả y hệt từ Java 6.”

Mục `Since` hỗ trợ kết luận đầu. Kết luận sau cần đối chiếu thêm và có thể không đúng.

### 4.5. Since không bảo đảm môi trường hiện tại cung cấp được API

Một API có mốc cũ vẫn có thể thuộc module không có trong runtime tùy biến, có phụ thuộc môi trường hoặc có ràng buộc sử dụng riêng. API thư viện ngoài còn cần đúng phiên bản dependency.

Do đó, kiểm tra mốc xuất hiện là một phần của việc xác minh khả năng dùng API, không thay thế kiểm tra module, dependency, cấu hình và runtime.

## 5. Ví dụ đối chiếu cụ thể trên Javadoc hiện hành

### 5.1. String.isEmpty(): mốc Java 6, kiểm tra độ dài

Mở phần chi tiết `String.isEmpty()` trong tài liệu hiện hành:

- Kết quả là `true` khi độ dài chuỗi bằng 0.
- Mốc được ghi là `1.6`.
- Kiểm tra rỗng không đồng nghĩa kiểm tra chỉ có khoảng trắng.

Chuỗi `"  "` có hai ký tự space nên không rỗng. Thông tin API hiện hành còn dẫn tới `isBlank()` khi mục tiêu là kiểm tra chuỗi chỉ gồm khoảng trắng.

Nhưng liên kết từ phương thức cũ sang phương thức mới không làm `isBlank()` trở thành API Java 6.

### 5.2. String.isBlank(): mốc Java 11, ý nghĩa khác

`isBlank()` trả `true` khi chuỗi rỗng hoặc chỉ chứa các code point được xem là khoảng trắng theo định nghĩa mà API dẫn tới. Mốc của phương thức là 11.

Vậy với `"  "`:

```text
isEmpty() → false
isBlank() → true
```

Đây là khác biệt hợp đồng, không chỉ khác biệt phiên bản.

Không tự viết lại quy tắc khoảng trắng bằng suy luận “ký tự có mã nhỏ hơn hoặc bằng space” nếu Javadoc đang dùng một định nghĩa khác. Theo liên kết tới `Character.isWhitespace(int)` khi cần hiểu chính xác.

### 5.3. NavigableMap: kiểu mới của Java 6 nhưng cần đọc từng quan hệ

Trang `NavigableMap` ghi `Since: 1.6`. Nó bổ sung các thao tác tìm theo thứ tự, chẳng hạn:

| Phương thức | Khóa được tìm so với khóa mục tiêu |
| --- | --- |
| `lowerKey(k)` | Nhỏ hơn k |
| `floorKey(k)` | Nhỏ hơn hoặc bằng k |
| `ceilingKey(k)` | Lớn hơn hoặc bằng k |
| `higherKey(k)` | Lớn hơn k |

Với khóa 10 và 20, tìm theo mục tiêu 15 cho `floorKey(15)=10` và `ceilingKey(15)=20`.

Tuy nhiên, `Since` không nói hết cách dùng. Cần đọc rằng khi không có khóa phù hợp, các thao tác đó có thể trả `null`, và thứ tự được xét theo quy tắc sắp xếp của map.

Nếu chỉ nhớ “NavigableMap là Java 6”, người học vẫn có thể viết sai khi tự động unbox một kết quả `null` thành `int`.

### 5.4. List.of: kiểu List cũ không kéo phương thức này về cùng mốc

`List.of(E, E)` trên tài liệu hiện hành có mốc 9. Nó tạo danh sách không cho sửa cấu trúc/nội dung bằng các phương thức thay đổi của List; phần tử `null` không được chấp nhận.

Biết phương thức có từ Java 9 chưa đủ: sau khi tạo List, lời gọi `add` sẽ thất bại vì đặc tính danh sách được trả về.

Cần đọc cả phần mô tả chung về các danh sách không sửa được mà phương thức liên kết tới. “Không sửa được danh sách” cũng không có nghĩa mọi đối tượng phần tử bên trong đều bất biến.

### 5.5. Phương thức mới có thể nằm ngay trên một interface quen thuộc

Ví dụ `List.reversed()` trong tài liệu hiện hành có mốc 21. Việc một lập trình viên đã dùng List nhiều năm không chứng minh phương thức này có trên runtime cũ.

Khi học Java 6, có thể ghi nhận đây là API bổ sung sau để tránh nhầm phạm vi, không đưa nó vào một ví dụ được giới thiệu là chỉ dùng API xuất hiện ở Java 6.

## 6. Không nhầm Since với Deprecated since

Có hai dạng rất dễ nhầm:

```text
Since: 1.6
```

và một annotation kiểu:

```java
@Deprecated(since = "17", forRemoval = false)
```

Annotation ở đây là ví dụ hình thức để phân biệt ý nghĩa, không phải khuyến nghị dùng một API lỗi thời cụ thể.

- Mục Javadoc `Since` nói về thời điểm phần tử xuất hiện.
- Giá trị `since` trong `@Deprecated` nói về thời điểm phần tử bắt đầu bị đánh dấu không khuyến khích sử dụng.
- `forRemoval=true` thể hiện ý định loại bỏ về sau, không phải phiên bản phần tử ra đời.

Một phần tử có thể có mốc xuất hiện rất sớm rồi chỉ bị đánh dấu deprecated nhiều phiên bản sau đó. Hai mốc không mâu thuẫn vì đang trả lời hai câu hỏi khác nhau.

Để học kiến thức còn phù hợp hiện nay, cần đọc cảnh báo deprecated và phương án thay thế nếu có. Nhưng cũng không kết luận “có từ Java 6 nên đã lỗi thời”: nhiều API được đưa vào từ Java 6 vẫn là công cụ đang dùng bình thường.

Nếu trang hiện hành có nhãn Preview hoặc nhãn trạng thái đặc biệt khác, phải đọc điều kiện sử dụng. Một con số `Since` không tự biến API preview thành một cam kết API ổn định.

## 7. Ví dụ chạy được: đọc phiên bản và hợp đồng cùng lúc

Tệp `JavadocCheck.java`:

```java
import java.util.List;
import java.util.NavigableMap;
import java.util.TreeMap;

public final class JavadocCheck {
    public static void main(String[] args) {
        String spaces = "  ";
        System.out.println("empty=" + spaces.isEmpty());
        System.out.println("blank=" + spaces.isBlank());

        NavigableMap<Integer, String> levels = new TreeMap<>();
        levels.put(10, "basic");
        levels.put(20, "advanced");
        System.out.println("floor15=" + levels.floorKey(15));
        System.out.println("ceiling15=" + levels.ceilingKey(15));

        List<String> names = List.of("An", "Binh");
        System.out.println("names=" + names);
        try {
            names.add("Chi");
        } catch (UnsupportedOperationException expected) {
            System.out.println("add=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17+:

```powershell
javac --release 17 -d out17 JavadocCheck.java
java -cp out17 JavadocCheck
```

Chỉ chạy lệnh thứ hai sau khi biên dịch thành công.

Stdout:

```text
empty=false
blank=true
floor15=10
ceiling15=20
names=[An, Binh]
add=UnsupportedOperationException
```

Ví dụ đã được biên dịch với `--release 17` và chạy kiểm tra trên JDK 24.0.2.

Cách đọc kết quả:

1. `empty=false` và `blank=true` xác nhận hai phương thức khác ý nghĩa.
2. Hai phép tìm khóa xác nhận hướng quan hệ của `floor`/`ceiling`.
3. Dòng List xác nhận danh sách được tạo thành công.
4. Lỗi `add` được ứng dụng bắt và in tên loại ngoại lệ, xác nhận phải đọc hợp đồng của kết quả trả về.

Đây là một ví dụ **hiện đại dùng cả API xuất hiện ở nhiều phiên bản**, không phải một chương trình có thể chạy nguyên văn trên Java 6. Cú pháp diamond `<>` trong `new TreeMap<>()` cũng không phải cú pháp Java 6. Không gán toàn bộ ví dụ về phiên bản của một API duy nhất bên trong.

Bảng ghi nhận cho ví dụ:

| Phần tử được sử dụng | Mốc đối chiếu | Kết luận |
| --- | --- | --- |
| `String.isEmpty()` | 1.6 | Có thể học như API bổ sung từ Java 6 và vẫn dùng hiện nay |
| `NavigableMap` | 1.6 | Kiểu thuộc bổ sung Java 6; vẫn cần đọc hợp đồng từng thao tác |
| `List.of(E, E)` | 9 | Không gán về Java 6 chỉ vì kết quả là List |
| `String.isBlank()` | 11 | Ví dụ hiện đại cần phiên bản đủ mới |

Bảng chỉ ghi những mốc đã đối chiếu, không phải kết luận toàn bộ chương trình hỗ trợ phiên bản tối thiểu nào.

## 8. Dùng javac --release để kiểm tra thêm

`Since` là bằng chứng tài liệu. Biên dịch theo release mục tiêu bổ sung một bước kiểm tra thực tế cho mã nguồn và bề mặt API nền tảng.

Ví dụ, trên JDK của lần kiểm tra có hỗ trợ release 8:

```powershell
javac --release 8 -d out8 JavadocCheck.java
```

Lần biên dịch này **được kỳ vọng thất bại** vì mã gọi `String.isBlank()` và `List.of(...)`, là các API không có trong Java 8.

Phần quan trọng của chẩn đoán là trình biên dịch không tìm thấy hai phương thức đó trong API release mục tiêu. Dòng báo lỗi, số dòng, ngôn ngữ và cảnh báo phụ thuộc JDK, nên không lấy một khối chẩn đoán cố định làm điều kiện cho mọi máy.

Trên JDK 24.0.2 đã kiểm tra, hai lỗi tương ứng với `isBlank()` và `List.of(String, String)` xuất hiện đúng như dự đoán.

### --release làm gì?

Nó đồng thời hướng việc biên dịch tới:

- Quy tắc ngôn ngữ của release được chỉ định.
- Dạng class file tương ứng.
- API Java SE/JDK được cung cấp cho release đó trong phạm vi trình biên dịch hỗ trợ.

Khác với chỉ đặt mức cú pháp hoặc chỉ đặt phiên bản class file, nó giúp tránh vô tình dùng một API nền tảng mới khi đang nhắm phiên bản cũ.

### --release không làm gì?

Nó không:

- Biến mọi thư viện bên ngoài thành tương thích với runtime mục tiêu.
- Tự kiểm chứng hành vi của mọi đường chạy.
- Bảo đảm ứng dụng thực tế không phụ thuộc môi trường mới hơn.
- Tự chạy chương trình trên đúng JVM mục tiêu.
- Hỗ trợ vô hạn mọi release Java trong lịch sử.

Xem `javac --help` để biết các release được hỗ trợ bởi trình biên dịch đang dùng. Không mặc nhiên thay số 8 trong ví dụ thành 6 rồi khẳng định mọi JDK hiện đại sẽ chấp nhận.

Mục tiêu của lần thử release 8 là chứng minh API mới bị phát hiện khi nhắm một release được hỗ trợ, không phải một quy trình khuyến nghị triển khai Java 8 hay Java 6 cho dự án mới.

Cũng không kết luận “biên dịch release 8 thất bại” xác định được chính xác một API ra đời ở 9 hay 11. Để biết mốc cụ thể, quay lại thông tin tài liệu của đúng phần tử.

## 9. Phân biệt hợp đồng với ghi chú triển khai

Javadoc hiện hành có thể có những phần như:

| Nhãn | Cách đọc |
| --- | --- |
| Mô tả chính, Parameters, Returns, Throws | Hợp đồng và điều kiện sử dụng cần hiểu |
| API Note | Hướng dẫn, lý do hoặc cách sử dụng bổ sung |
| Implementation Requirements | Yêu cầu đối với phần triển khai được mô tả |
| Implementation Note | Chi tiết hoặc đặc điểm của phần triển khai, cần xét ngữ cảnh |
| Since | Thông tin mốc xuất hiện, không phải toàn bộ hợp đồng |
| See Also | Liên kết cần theo khi giúp làm rõ ngữ nghĩa |

Không biến một chi tiết triển khai của một bản JDK thành quy tắc bắt buộc cho mọi JVM và mọi phiên bản. Ngược lại, không bỏ qua phần Returns/Throws rồi tự đoán hành vi chỉ từ một ví dụ.

Khi một ví dụ chạy khác kỳ vọng, hãy kiểm tra theo thứ tự: đúng API/overload chưa, đúng dữ liệu đầu vào chưa, đã đọc ràng buộc chưa, runtime có đúng phiên bản đang xem tài liệu không. Chỉ sau đó mới xem xét khả năng lỗi triển khai hoặc khác biệt phiên bản.

## 10. Cách ghi chú API để dễ kiểm tra lại

Một ghi chú hữu ích có thể theo mẫu:

```text
Phần tử: java.lang.String.isEmpty()
Tài liệu đang đọc: Java SE 27
Mốc Since của phương thức: 1.6
Hợp đồng chính: true khi độ dài bằng 0
Điểm không được nhầm: chuỗi toàn khoảng trắng chưa chắc rỗng
Phiên bản ví dụ biên dịch: --release 17
Liên kết: phần chi tiết isEmpty() trên Javadoc chính thức
```

Đây là mẫu ghi chép, không phải dữ liệu cần tự động thêm vào chương trình.

Với một API có overload, bổ sung kiểu tham số. Với thư viện ngoài, ghi cả tọa độ dependency và phiên bản bộ tài liệu. Nếu chưa xác minh được mốc, ghi rõ chưa xác minh thay vì điền một giá trị suy đoán.

Bằng chứng tài liệu và bằng chứng chạy mã bổ sung cho nhau: tài liệu nêu hợp đồng, ví dụ kiểm tra một tập đầu vào. Một ví dụ trả đúng không chứng minh mọi trường hợp đều đúng; một mốc Since cũng không thay thế việc hiểu kết quả.

## 11. Lỗi thường gặp

### Chọn nhầm phiên bản tài liệu

Đang xây ứng dụng release 17 nhưng sao chép API chỉ có từ 21 vì kết quả tìm kiếm mở trang mới hơn. Giải pháp là đọc mốc từng phần tử và biên dịch theo mục tiêu, không chỉ kiểm tra IDE gợi ý được tên.

### Dùng Since của package/module cho mọi kiểu bên trong

Package hoặc module có mốc riêng, từng kiểu/thành viên cũng có thể có mốc riêng. Đơn vị kết luận phải khớp đơn vị bằng chứng.

### Coi API cũ là API đã hết giá trị

Mốc ra đời sớm không đồng nghĩa bị loại bỏ hoặc không nên dùng. Đánh giá trạng thái và hợp đồng hiện hành.

### Coi API mới hơn luôn thay thế hoàn toàn API cũ

`isBlank()` không làm `isEmpty()` mất ý nghĩa: kiểm tra độ dài bằng 0 và kiểm tra chỉ có khoảng trắng là hai nhu cầu khác nhau.

### Chỉ kiểm tra biên dịch

Một lời gọi `names.add(...)` có thể biên dịch hợp lệ nhưng thất bại với danh sách do `List.of` trả về. Trình biên dịch không thay thế phần mô tả hành vi.

### Nhầm phiên bản tài liệu, phiên bản API và phiên bản chạy ví dụ

Một đoạn mã được thử bằng JDK 24 không có nghĩa mọi API trong nó ra đời ở 24. Một trang Javadoc 27 cũng có thể mô tả API từ 1.6. Ghi ba con số theo ba vai trò.

## 12. Bài tập tự kiểm chứng

1. Mở trang String hiện hành, tìm đúng `isEmpty()` và `isBlank()`. Ghi hai mốc Since và giải thích kết quả với `""`, `" "`, `"a"`.
2. Với NavigableMap chứa 10 và 20, dự đoán `floorKey(10)`, `lowerKey(10)`, `ceilingKey(20)`, `higherKey(20)`. Kiểm tra trường hợp không có kết quả mà không tự động unbox thành `int`.
3. Tìm overload `List.of(E, E)`. Đọc cách xử lý phần tử null và khả năng sửa danh sách. Đừng chỉ ghi số phiên bản.
4. Mở `List.reversed()`, ghi mốc của chính phương thức. Giải thích vì sao việc List tồn tại trước đó không đủ để dùng phương thức này trên JDK 17.
5. Trong ví dụ chạy, bỏ hai lời gọi API mới khiến release 8 báo lỗi rồi thử lại nếu trình biên dịch hỗ trợ. Phân biệt “biên dịch được theo release 8” với “chứng minh toàn bộ mã thuộc Java 6”.
6. Đưa ra một ghi chú có riêng ba dòng: phiên bản Javadoc, mốc Since của phần tử và phiên bản runtime thử nghiệm.

Sau bài, cần hình thành thói quen **tìm đúng phần tử, đọc đủ hợp đồng, đối chiếu đúng Since và kiểm tra theo phiên bản mục tiêu**. Đây là kỹ năng dùng lại được khi học API Java 6 trên JDK hiện đại và khi làm việc với những phiên bản về sau.

## Tài liệu đối chiếu

- [String — Javadoc Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): `isEmpty()`, `isBlank()` và hợp đồng chuỗi.
- [NavigableMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/NavigableMap.html): vai trò, quan hệ tìm khóa và mốc 1.6.
- [List](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): các overload `of`, danh sách không sửa được và các phương thức bổ sung sau.
- [Đặc tả Javadoc — thẻ since](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html#since): ý nghĩa và phạm vi của thông tin Since.
- [Deprecated](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Deprecated.html): phân biệt mốc bắt đầu deprecated.
- [javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): tùy chọn `--release` và giới hạn phiên bản hỗ trợ.
