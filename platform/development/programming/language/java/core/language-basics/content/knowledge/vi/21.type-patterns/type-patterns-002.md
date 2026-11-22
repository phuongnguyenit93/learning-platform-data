# Type pattern kết hợp kiểm tra kiểu và khai báo biến — Java 17+

**Type pattern** của `instanceof` cho phép Java vừa kiểm tra kiểu runtime, vừa khai báo **biến có kiểu tĩnh phù hợp** khi phép kiểm tra thành công. Đây là tính năng chuẩn từ Java 16, dùng được trên Java 17 **không cần bật preview**.

~~~java
Object value = "Hello";

if (value instanceof String text) {
    System.out.println(text.length()); // 5
}
~~~

Cú pháp `expression instanceof Type variable` thực hiện ba việc: kiểm tra đối tượng có tương thích với `Type`; nếu đúng, ràng buộc đối tượng với biến `variable`; cho phép dùng biến trong **phạm vi mà compiler chắc chắn pattern đã khớp** (*flow scoping*).

## 1. Khác gì với `instanceof` truyền thống?

Cách cũ phải ép kiểu rõ ràng sau khi kiểm tra:

~~~java
Object obj = "Java";
if (obj instanceof String) {
    String text = (String) obj;
    System.out.println(text.toUpperCase());
}
~~~

Cách dùng type pattern:

~~~java
Object obj = "Java";
if (obj instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Cả hai đều in `JAVA`. Type pattern bỏ phép cast lặp lại nhưng **không tạo đối tượng mới**, không biến `obj` thành một biến khai báo `String`, và không thay đổi giá trị đối tượng.

| Khía cạnh | Kiểm tra cũ | Type pattern |
| --- | --- | --- |
| Kiểm tra kiểu | `obj instanceof String` | `obj instanceof String text` |
| Dùng như `String` | `(String) obj` | Biến `text` đã có kiểu `String` |
| Đối tượng mới? | Không | Không |
| `obj == null` | Kết quả false | Kết quả false |
| Tính an toàn | Phải cast đúng | Compiler xác định phạm vi biến mẫu |

## 2. Chương trình Java 17+ chạy độc lập

Tạo tệp UTF-8 tên **`TypePatternDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;

public class TypePatternDemo {
    static void describe(Object value) {
        if (value instanceof String text) {
            System.out.println("string=" + text.toUpperCase(Locale.ROOT)
                    + ",length=" + text.length());
        } else if (value instanceof Integer number) {
            System.out.println("integerTwice=" + (number * 2));
        } else if (value == null) {
            System.out.println("null");
        } else {
            System.out.println("other="
                    + value.getClass().getSimpleName());
        }
    }

    static String normalize(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            return "invalid";
        }
        return text.trim().toLowerCase(Locale.ROOT);
    }

    static String classify(Object input) {
        if (input instanceof String text && text.length() >= 3) {
            return "long-enough:" + text;
        }
        return "other";
    }

    static int lengthOf(Object value) {
        if (value instanceof CharSequence chars) {
            return chars.length();
        }
        return -1;
    }

    public static void main(String[] args) {
        System.out.println("== old versus pattern ==");
        Object first = "Hello";
        if (first instanceof String) {
            String oldText = (String) first;
            System.out.println("old=" + oldText.substring(0, 2));
        }
        if (first instanceof String text) {
            System.out.println("pattern=" + text.substring(0, 2));
        }

        System.out.println("== matching types ==");
        describe("Java");
        describe(21);
        describe(3.5);
        describe(null);

        System.out.println("== guards and flow scope ==");
        System.out.println("normalize1=" + normalize("  JAVA  "));
        System.out.println("normalize2=" + normalize("   "));
        System.out.println("normalize3=" + normalize(12));
        System.out.println("normalize4=" + normalize(null));
        System.out.println("classifyCat=" + classify("cat"));
        System.out.println("classifyHi=" + classify("hi"));
        System.out.println("classifyNull=" + classify(null));

        System.out.println("== null and interfaces ==");
        Object missing = null;
        System.out.println("nullMatches="
                + (missing instanceof String candidate));
        System.out.println("lengthString=" + lengthOf("abc"));
        System.out.println("lengthNumber=" + lengthOf(42));
        Object integer = 7;
        if (integer instanceof Number number) {
            System.out.println("numberValue=" + number.intValue());
        }

        System.out.println("== generic wildcard ==");
        Object unknown = List.of("A", "B");
        if (unknown instanceof List<?> items) {
            System.out.println("listSize=" + items.size());
            System.out.println("firstItem=" + items.get(0));
        }

        System.out.println("== branch scope ==");
        Object item = "ready";
        if (item instanceof String text) {
            System.out.println("then=" + text);
        } else {
            System.out.println("else=not-a-string");
        }
        System.out.println("done");
    }
}
~~~

Chạy với **JDK 17 trở lên** trong PowerShell hoặc Bash tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 TypePatternDemo.java
java TypePatternDemo
~~~

**Expected stdout chính xác** của riêng lệnh `java TypePatternDemo`:

~~~text
== old versus pattern ==
old=He
pattern=He
== matching types ==
string=JAVA,length=4
integerTwice=42
other=Double
null
== guards and flow scope ==
normalize1=java
normalize2=invalid
normalize3=invalid
normalize4=invalid
classifyCat=long-enough:cat
classifyHi=other
classifyNull=other
== null and interfaces ==
nullMatches=false
lengthString=3
lengthNumber=-1
numberValue=7
== generic wildcard ==
listSize=2
firstItem=A
== branch scope ==
then=ready
done
~~~

Các lệnh `java -version` và `javac -version` hiển thị thông tin phiên bản phụ thuộc môi trường, không thuộc phần stdout cố định.

## 3. Flow scoping qua ví dụ ngắn

Biến mẫu chỉ dùng được ở những nhánh mà trình biên dịch chứng minh kiểm tra kiểu đã thành công. Với `&&`, vế phải chỉ chạy khi `input instanceof String text` đúng; với `||` đặt ngay sau phép kiểm tra dương, vế phải lại chạy khi mẫu không khớp nên không được dùng `text` ở đó.

~~~java
static String normalize(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return "INVALID";
    }
    return text.strip();
}
~~~

Ở guard phủ định, nếu Java phải tính `text.isBlank()`, điều kiện `!(...)` đã false nên `text` được ràng buộc. Sau guard `return`, mọi đường đi còn lại cũng chắc chắn khớp String. Trái lại, `text` không dùng được ở nhánh `else` của phép kiểm tra dương. Bài về phạm vi biến mẫu sẽ phân tích đầy đủ `if/else`, `!`, `&&`, `||` và toán tử ba ngôi.

## 4. `null`, kiểu cha và interface

~~~java
Object value = null;
boolean matched = value instanceof String text; // false.
~~~

`instanceof` type pattern với `null` **trả false**, không tự ném `NullPointerException`. Trái lại, nếu sau đó gọi phương thức trên `value` mà chưa kiểm tra, vẫn có thể gặp lỗi null.

Pattern kiểm tra **kiểu đối tượng tại runtime** theo quan hệ lớp kế thừa/interface:

~~~java
Object value = "abc";
if (value instanceof CharSequence chars) {
    System.out.println(chars.length()); // 3.
}
~~~

`String` triển khai `CharSequence` nên pattern khớp. Biến `chars` có kiểu tĩnh `CharSequence`; chỉ dùng trực tiếp các phương thức có trong kiểu đó, không tự có toàn bộ phương thức chuyên biệt của `String`.

Trong chuỗi `if/else if`, pattern kiểu cha được đặt trước có thể bắt cả đối tượng kiểu con. Chọn thứ tự theo nghiệp vụ, tránh nhánh con không bao giờ đạt tới do kiểu cha đã xử lý trước.

## 5. Giới hạn và lỗi biên dịch thường gặp

| Tình huống | Đúng hay sai? |
| --- | --- |
| `Object o; o instanceof String s` | Hợp lệ khi `o` đã được khởi tạo |
| `o instanceof String s && s.length() > 0` | Hợp lệ theo flow scoping |
| `o instanceof String s || s.length() > 0` | **Sai**: s có thể chưa ràng buộc ở vế phải |
| `String s = "x"; s instanceof String t` | **Sai khi biên dịch**: kiểu tĩnh luôn là subtype của kiểu pattern |
| `o instanceof List<?> items` | Hợp lệ với kiểu wildcard có thể kiểm tra |
| `o instanceof List<String> items` | Không hợp lệ với `Object o`: type erasure |
| `null instanceof String s` | Không dùng literal `null` làm biểu thức mẫu trực tiếp; dùng biến tham chiếu có giá trị null như ví dụ trên |

**Generic:** Do *type erasure*, Java không thể xác thực đối tượng là `List<String>` chỉ từ thông tin runtime `List`. Pattern `List<?> items` là hợp lệ, nhưng `items.get(0)` trả `Object` theo kiểu tĩnh; muốn coi phần tử là String thì cần kiểm tra từng phần tử riêng.

**Kiểu nguyên thủy:** `instanceof` type pattern dùng cho **kiểu tham chiếu**, không viết `instanceof int x`. Một giá trị `int` được gán vào `Object` sẽ được boxing thành `Integer`, và có thể kiểm tra bằng `instanceof Integer number`.

**Pattern quá hiển nhiên:** Nếu biểu thức trái có kiểu tĩnh `String` và kiểm tra `instanceof String text`, Java 17 từ chối vì phép kiểm tra luôn đúng theo quan hệ subtype; hãy sử dụng chính biến đã có kiểu String.

## 6. Java 17 so với các loại pattern mới hơn

`instanceof Type variable` là tính năng **chuẩn** của Java 17. Nhưng `case String s -> ...` trong **pattern matching for switch** chưa là tính năng chuẩn ở Java 17 (chỉ có preview với điều kiện bật riêng); không tự suy ra có thể dùng type pattern `case` trong switch Java 17 thông thường.

**Record patterns** cũng chưa được chuẩn hóa ở Java 17. Đây là các tính năng khác với kiểm tra kiểu và ràng buộc một biến qua `instanceof`.

## 7. Bài tập tự kiểm tra

1. `Object x = "abc"; if (x instanceof String s) ...` thì `s.length()` bằng mấy?  
   *Đáp án:* 3.
2. `Object x = null; x instanceof String s` cho gì?  
   *Đáp án:* false.
3. Vì sao `x instanceof String s && s.isBlank()` có thể biên dịch?  
   *Đáp án:* `&&` chỉ đánh giá vế phải khi pattern khớp.
4. Vì sao thay `&&` bằng `||` ở ví dụ trên thường sai?  
   *Đáp án:* Vế phải của `||` có thể chạy khi pattern không khớp và s chưa được ràng buộc.
5. Sau `if (!(x instanceof String s)) return;`, có thể dùng `s` ở lệnh tiếp không?  
   *Đáp án:* Có, vì trường hợp không khớp đã thoát phương thức.
6. `Object x = List.of("a"); x instanceof List<String> items` có hợp lệ không?  
   *Đáp án:* Không; thay bằng `List<?>` và kiểm tra phần tử nếu cần.
7. Có thể dùng `instanceof Integer n` cho giá trị chứa trong `Object` không?  
   *Đáp án:* Có nếu thực tế đối tượng là `Integer`.

## Checklist

- [ ] `instanceof Type variable` vừa kiểm tra kiểu vừa khai báo biến mẫu có kiểu tĩnh phù hợp.
- [ ] Biến mẫu chỉ được dùng theo **flow scoping**, không tự tồn tại trong nhánh thất bại.
- [ ] Nắm cách dùng `&&` và guard với `!` để bảo đảm đã khớp.
- [ ] `null` không khớp type pattern.
- [ ] Hiểu quan hệ kế thừa và interface khi chọn kiểu pattern.
- [ ] Không dùng generic cụ thể như `List<String>` trong `instanceof` theo cách không thể kiểm tra runtime.
- [ ] Không nhầm type pattern `instanceof` với pattern-switch/record pattern của Java mới.

**Kết luận:** Type pattern giúp mã Java 17 giảm cast thủ công, nhưng điều quan trọng nhất là **trạng thái kiểm tra kiểu và phạm vi biến đi theo luồng điều khiển**. Dùng `instanceof` với `&&`, kiểm tra null và guard clause đúng cách để viết mã rõ ràng, an toàn.
