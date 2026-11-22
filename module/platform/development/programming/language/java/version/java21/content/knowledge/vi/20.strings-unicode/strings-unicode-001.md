# String.indexOf với khoảng beginIndex và endIndex

Java 21 bổ sung hai overload của String.indexOf cho phép giới hạn vùng tìm kiếm trực tiếp: indexOf(int ch, int beginIndex, int endIndex) và indexOf(String str, int beginIndex, int endIndex). Cả hai tìm trong khoảng bắt đầu tại beginIndex và dừng trước endIndex, tức khoảng nửa mở [beginIndex, endIndex).

Các overload này hữu ích khi phân tích một vùng con của chuỗi mà không muốn tạo một substring trung gian. Cần nhớ rằng chỉ số của String được tính theo UTF-16 code unit, kể cả khi tìm một Unicode code point nằm ngoài Basic Multilingual Plane.

## 1. Hai overload mới từ Java 21

Java 21 cung cấp hai chữ ký:

~~~java
public int indexOf(int ch, int beginIndex, int endIndex)

public int indexOf(String str, int beginIndex, int endIndex)
~~~

- Overload nhận int ch tìm một ký tự/code point.
- Overload nhận String str tìm một chuỗi con.
- beginIndex là vị trí bắt đầu được tính vào vùng tìm kiếm.
- endIndex là vị trí dừng, không được tính vào vùng tìm kiếm.

Cả hai phương thức trả về chỉ số xuất hiện đầu tiên nếu tìm thấy; nếu không có kết quả trong vùng đã chọn, chúng trả về -1.

Các phương thức này là API chính thức từ Java 21, không phải preview feature.

## 2. Hiểu khoảng tìm kiếm [beginIndex, endIndex)

Khoảng tìm kiếm dùng quy ước nửa mở:

- Bao gồm vị trí beginIndex.
- Không bao gồm vị trí endIndex.
- Độ dài vùng tìm kiếm là endIndex - beginIndex.

Ví dụ:

~~~java
String text = "one|two|three";

int separator = text.indexOf('|', 4, 13);
int word = text.indexOf("two", 4, 7);
int outside = text.indexOf("two", 5, 7);

System.out.println(separator); // 7
System.out.println(word);      // 4
System.out.println(outside);   // -1
~~~

Chuỗi có các vị trí:

~~~text
index:  0 1 2 3 4 5 6 7 8 9 10 11 12
text:   o n e | t w o | t h  r  e  e
                    ^
                    vị trí 7
~~~

Lời gọi indexOf('|', 4, 13) chỉ xét các vị trí từ 4 đến 12, nên tìm thấy dấu | tại 7. Lời gọi indexOf("two", 4, 7) tìm được từ vị trí 4. Khi bắt đầu ở 5, vùng [5, 7) không chứa đủ chuỗi "two", nên kết quả là -1.

Với overload tìm chuỗi con, toàn bộ chuỗi cần tìm phải nằm trong vùng được chỉ định. Một phần của chuỗi bắt đầu trong vùng nhưng kéo dài vượt quá endIndex không được xem là kết quả hợp lệ.

## 3. Tìm một ký tự hoặc Unicode code point

Overload nhận int ch cho phép truyền một Unicode code point. Quy tắc so sánh phụ thuộc giá trị của ch:

- Nếu ch nằm trong khoảng U+0000 đến U+FFFF, phương thức so sánh với charAt(k).
- Nếu ch lớn hơn U+FFFF, phương thức so sánh với codePointAt(k).

Ví dụ tìm ký tự ASCII:

~~~java
String text = "name=Lan;role=admin";

int equals = text.indexOf('=', 0, text.length());
int semicolon = text.indexOf(';', 5, text.length());

System.out.println(equals);    // 4
System.out.println(semicolon); // 8
~~~

Ví dụ tìm một code point nằm ngoài BMP:

~~~java
String text = "A😀B";

int emoji = text.indexOf(0x1F600, 0, text.length());

System.out.println(emoji); // 1
System.out.println(text.length()); // 4
~~~

Kết quả là 1 vì emoji bắt đầu ở vị trí UTF-16 code unit số 1. Emoji này được biểu diễn bằng một surrogate pair, chiếm hai char ở vị trí 1 và 2; ký tự B nằm ở vị trí 3. Vì vậy length() trả về 4, dù chuỗi có ba Unicode code point.

Điểm cần nhớ: overload nhận int ch hiểu ch là code point khi giá trị lớn hơn U+FFFF, nhưng chỉ số trả về vẫn là chỉ số UTF-16 code unit. Đây không phải chỉ số thứ tự của code point trong chuỗi, cũng không phải chỉ số grapheme cluster mà người dùng nhìn thấy.

Với code point ngoài BMP, codePointAt(k) đọc surrogate pair bắt đầu tại k. Nếu vùng dữ liệu cần tìm phải chứa trọn code point đó, hãy chọn beginIndex và endIndex sao cho không cắt vùng ngay giữa hai code unit của surrogate pair.

## 4. Tìm một chuỗi con trong vùng giới hạn

Overload nhận String str tìm lần xuất hiện đầu tiên của str trong vùng chỉ định. Hợp đồng API quy định kết quả tương đương với:

~~~java
int result = text.substring(beginIndex, endIndex).indexOf(str);
if (result >= 0) {
    result += beginIndex;
}
~~~

Tuy nhiên, bản thân indexOf(String, int, int) không tạo một đối tượng substring trung gian. Đây là lợi ích hữu ích khi cần tìm trong một vùng của chuỗi lớn.

Ví dụ phân tích một dòng log:

~~~java
String line = "2026-11-16 INFO user=42 action=login";

int fieldsStart = line.indexOf("user=", 16, line.length());
int actionStart = line.indexOf("action=", 16, line.length());

System.out.println(fieldsStart); // 16
System.out.println(actionStart); // 24
~~~

Có thể dùng vùng giới hạn để tìm một dấu phân cách sau một trường cụ thể:

~~~java
String record = "id=42;role=admin;active=true";

int roleStart = record.indexOf("role=", 0, record.length());
int roleEnd = record.indexOf(';', roleStart, record.length());

String role = record.substring(
    roleStart + "role=".length(),
    roleEnd
);

System.out.println(role); // admin
~~~

Trong ví dụ này, indexOf xác định vị trí đầu và cuối của trường role. substring chỉ được dùng sau đó để trích xuất giá trị cần thiết.

## 5. Kiểm tra beginIndex và endIndex

Hai overload có khoảng tìm kiếm kiểm tra tính hợp lệ của các chỉ số. Phương thức ném StringIndexOutOfBoundsException nếu:

- beginIndex < 0.
- endIndex > text.length().
- beginIndex > endIndex.

Ví dụ:

~~~java
String text = "Java 21";

// beginIndex âm: ném StringIndexOutOfBoundsException
text.indexOf('J', -1, 4);

// endIndex vượt quá length(): ném StringIndexOutOfBoundsException
text.indexOf("21", 5, 20);

// beginIndex lớn hơn endIndex: ném StringIndexOutOfBoundsException
text.indexOf('a', 5, 2);
~~~

Các trường hợp biên hợp lệ:

~~~java
String text = "Java";

System.out.println(text.indexOf('J', 0, 0));  // -1
System.out.println(text.indexOf('J', 0, 1));  // 0
System.out.println(text.indexOf("Java", 0, 4)); // 0
System.out.println(text.indexOf("Java", 0, 3)); // -1
System.out.println(text.indexOf("", 2, 2)); // 2
~~~

Khi beginIndex == endIndex, vùng tìm kiếm rỗng. Không có ký tự nào có thể được tìm thấy, nên overload nhận int ch trả về -1. Với chuỗi tìm kiếm rỗng, kết quả là chính beginIndex, theo quy tắc tìm chuỗi rỗng của String.indexOf.

Lưu ý: hai overload cũ nhận fromIndex có quy tắc khác. Chúng không ném exception chỉ vì fromIndex âm hoặc lớn hơn độ dài chuỗi; overload có cả beginIndex và endIndex kiểm tra vùng tìm kiếm chặt chẽ hơn.

## 6. So sánh với các overload indexOf cũ

| Cách gọi | Phạm vi tìm kiếm | Xử lý chỉ số ngoài phạm vi |
|---|---|---|
| indexOf(ch) | Toàn bộ chuỗi | Không có chỉ số đầu vào |
| indexOf(ch, fromIndex) | Từ fromIndex đến cuối chuỗi | fromIndex âm được xem như 0; lớn hơn length trả -1 |
| indexOf(ch, beginIndex, endIndex) | Khoảng [beginIndex, endIndex) | Ném StringIndexOutOfBoundsException nếu vùng không hợp lệ |
| indexOf(str) | Toàn bộ chuỗi | Không có chỉ số đầu vào |
| indexOf(str, fromIndex) | Tìm chuỗi con từ vị trí bắt đầu | fromIndex âm bắt đầu từ 0; lớn hơn length bắt đầu từ length (needle không rỗng sẽ không khớp) |
| indexOf(str, beginIndex, endIndex) | Chuỗi con phải nằm hoàn toàn trong khoảng đã chọn | Ném StringIndexOutOfBoundsException nếu vùng không hợp lệ |

Trước Java 21, để giới hạn cả hai đầu, có thể tạo substring rồi tìm bên trong:

~~~java
String text = "one|two|three";

int localIndex = text.substring(4, 7).indexOf("two");
int absoluteIndex = localIndex >= 0 ? localIndex + 4 : -1;
~~~

Từ Java 21, có thể viết trực tiếp:

~~~java
int absoluteIndex = text.indexOf("two", 4, 7);
~~~

Cách gọi mới ngắn hơn, giữ chỉ số theo chuỗi gốc và không tạo substring trung gian. Khi cần xử lý chuỗi lớn hoặc tìm trong nhiều vùng, điều này giúp tránh các object/copy trung gian không cần thiết.

## 7. Chỉ số String là UTF-16, không phải vị trí ký tự hiển thị

Java String lưu văn bản theo UTF-16. Các API dùng chỉ số như length(), charAt(), substring() và indexOf() biểu diễn vị trí bằng UTF-16 code unit.

Điều này dẫn đến ba khái niệm cần phân biệt:

- **UTF-16 code unit:** một giá trị char 16 bit; các API chỉ số của String dùng đơn vị này.
- **Unicode code point:** một giá trị mã Unicode; một code point có thể chiếm một hoặc hai UTF-16 code unit.
- **Grapheme cluster:** đơn vị ký tự mà người đọc thường cảm nhận, có thể gồm nhiều code point, ví dụ chữ cái kết hợp dấu.

indexOf(int ch, beginIndex, endIndex) có thể tìm code point ngoài BMP, nhưng chỉ số trả về vẫn là vị trí UTF-16. indexOf(String str, beginIndex, endIndex) tìm chuỗi con theo đúng chuỗi UTF-16 được biểu diễn; nó không thực hiện so khớp ngôn ngữ tự nhiên, không tự chuẩn hóa Unicode và không gộp các grapheme cluster.

Ví dụ, chữ é có thể được biểu diễn bằng một code point dựng sẵn (U+00E9) hoặc bằng e kết hợp dấu sắc (U+0065 U+0301). Hai chuỗi này nhìn giống nhau nhưng có chuỗi code point khác nhau; indexOf không tự xem chúng là bằng nhau. Nếu yêu cầu nghiệp vụ cần so khớp tương đương canonical, hãy chuẩn hóa cả chuỗi nguồn và chuỗi tìm kiếm bằng java.text.Normalizer trước khi tìm, đồng thời lưu ý chỉ số sau chuẩn hóa có thể không còn trỏ trực tiếp vào chuỗi gốc.

## 8. Ví dụ thực tế: tìm dấu phân cách trong một vùng

Giả sử chuỗi chứa nhiều phần được ngăn cách bằng dấu |, nhưng chỉ muốn tìm dấu phân cách bên trong một trường:

~~~java
String data = "header|name=Lan|role=admin|footer";

int nameStart = data.indexOf("name=", 0, data.length());
int roleStart = data.indexOf("role=", nameStart, data.length());

int endOfName = data.indexOf('|', nameStart, roleStart);
int endOfRole = data.indexOf('|', roleStart, data.length());

String name = data.substring(
    nameStart + "name=".length(),
    endOfName
);

String role = data.substring(
    roleStart + "role=".length(),
    endOfRole
);

System.out.println(name); // Lan
System.out.println(role); // admin
~~~

Các lần tìm dấu phân cách đều giới hạn vùng bắt đầu và kết thúc phù hợp. Cần kiểm tra -1 trước khi dùng chỉ số trả về để tính vị trí trích xuất trong code production; ví dụ trên giả định dữ liệu đầu vào đúng định dạng.

## 9. Lựa chọn overload phù hợp

- Dùng indexOf(ch) khi cần tìm trên toàn bộ chuỗi.
- Dùng indexOf(ch, fromIndex) khi chỉ cần giới hạn điểm bắt đầu và chấp nhận quy tắc xử lý fromIndex của overload cũ.
- Dùng indexOf(ch, beginIndex, endIndex) khi cần tìm code point trong một vùng có cả điểm đầu và điểm cuối được kiểm tra.
- Dùng indexOf(str, beginIndex, endIndex) khi cần tìm một chuỗi con nằm hoàn toàn trong vùng chỉ định.
- Dùng substring khi thực sự cần tạo/trả về phần chuỗi, không cần tạo substring chỉ để tìm kiếm.
- Nếu xử lý Unicode ngoài BMP, nhớ rằng giá trị int ch có thể là code point nhưng mọi chỉ số đầu vào/đầu ra vẫn là UTF-16 code unit.
- Nếu cần so khớp không phân biệt hoa thường, theo locale hoặc theo canonical equivalence, hãy áp dụng quy tắc chuẩn hóa/so khớp phù hợp trước hoặc trong quy trình tìm kiếm; indexOf thực hiện tìm kiếm chính xác theo chuỗi.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — String.indexOf(int, int, int)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#indexOf(int,int,int))
- [Java SE 21 API — String.indexOf(String, int, int)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#indexOf(java.lang.String,int,int))
- [Java SE 21 API — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java SE 21 API — java.text.Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)


