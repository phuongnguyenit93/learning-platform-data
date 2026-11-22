# So sánh `String` theo nội dung thay vì dựa vào `intern()` trong collection Java

## 1. Vấn đề thực tế

Hãy tưởng tượng ứng dụng nhận tên khóa `"java"` từ hai nguồn: một nơi viết trực tiếp trong source code, nơi khác đọc từ dữ liệu hoặc tạo chuỗi mới. Hai giá trị có nội dung giống hệt nhau, nhưng không nhất thiết là cùng **đối tượng `String`**.

~~~java
String a = "java";
String b = new String("java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Cả hai đều biểu thị bốn chữ cái `j`, `a`, `v`, `a`. Biểu thức `a == b` cho kết quả `false` vì hai biến tham chiếu đến **hai đối tượng khác nhau**. Biểu thức `a.equals(b)` cho kết quả `true` vì `String.equals` so sánh **nội dung chuỗi**.

Trong `Set<String>`, `Map<String, ...>` hay các phép loại bỏ giá trị trùng lặp, quy tắc nghiệp vụ thường là: **cùng nội dung thì được coi là cùng khóa hoặc cùng phần tử**. Vì thế cần dựa vào `equals()` và `hashCode()`, thay vì cố làm cho mọi chuỗi đều trỏ tới một đối tượng được `intern()`.

Một chương trình có thể "tình cờ chạy đúng" với `==` khi các giá trị đều là string literal, rồi thất bại khi dữ liệu đến từ file, mạng, cơ sở dữ liệu hoặc phép nối chuỗi ở runtime.

## 2. Phân biệt `==`, `equals()` và `intern()`

| Biểu thức / API | Điều nó kiểm tra hoặc thực hiện | Thích hợp khi |
| --- | --- | --- |
| `a == b` | Hai tham chiếu có trỏ tới cùng đối tượng hay không | Chủ ý kiểm tra **định danh đối tượng** |
| `a.equals(b)` | Hai `String` có cùng dãy UTF-16 code unit hay không | Kiểm tra **nội dung** chính xác, phân biệt chữ hoa/thường |
| `Objects.equals(a, b)` | So sánh nội dung an toàn khi một hoặc cả hai biến có thể `null` | So sánh giá trị nullable |
| `a.equalsIgnoreCase(b)` | So sánh không phân biệt hoa/thường theo quy tắc của Java | Khi nghiệp vụ xác định rõ cách so sánh này phù hợp |
| `a.intern()` | Trả về tham chiếu đại diện chuẩn (canonical) trong string pool cho nội dung của `a` | Trường hợp tối ưu hoặc kỹ thuật riêng có chủ đích |
| `a.hashCode()` | Tạo giá trị băm ổn định theo nội dung `String` | Collections dựa trên hash, như `HashSet` và `HashMap` |
| `a.compareTo(b)` | So sánh thứ tự từ điển theo các code unit UTF-16 | Sắp xếp theo **natural order** của `String` |

Điểm cần nhớ: `String.intern()` **không phải** phép kiểm tra hai chuỗi có bằng nhau hay không. Nó trả về một tham chiếu đại diện chuẩn, cho phép những chuỗi có nội dung bằng nhau chia sẻ một đối tượng sau khi intern. Nếu mục đích là **so sánh giá trị**, dùng `equals()` trực tiếp vừa rõ nghĩa vừa không phụ thuộc vào bước chuẩn hóa tham chiếu.

### `intern()` hoạt động như thế nào?

JVM duy trì một **string pool** cho các chuỗi được intern. String literal như `"java"` được intern. Khi gọi `someString.intern()`, kết quả là đối tượng đại diện chuẩn đang có cùng nội dung trong pool, hoặc một đối tượng trở thành đại diện cho nội dung đó nếu trước đó chưa tồn tại.

~~~java
String literal = "java";
String created = new String("java");

System.out.println(literal == created);          // false
System.out.println(literal == created.intern()); // true
System.out.println(created == created.intern()); // false
~~~

`created.intern()` **trả về một tham chiếu**; nó không thay nội dung và không biến chính đối tượng `created` thành string literal. Việc dùng `intern()` ở đây chỉ giải thích cơ chế, không phải giải pháp cần dùng cho so sánh trong collection.

Trường hợp `new String("java")` được tạo riêng là minh họa rõ ràng; với chuỗi được tối ưu hóa hoặc hằng biểu thức tại thời điểm biên dịch, không được suy luận máy móc rằng mọi biểu thức ghép chuỗi đều tạo đối tượng mới.

## 3. Kiểm chứng `intern()` không cần thiết cho hash collection

Hai instance mới chứa cùng chữ vẫn là **một** phần tử `HashSet` và **một** khóa `HashMap`. Không cần chuẩn hóa tham chiếu trước bằng `intern`:

~~~java
String a = new String("id-42");
String b = new String("id-42");

Set<String> set = new HashSet<>();
set.add(a);
set.add(b);
System.out.println(set.size()); // 1

Map<String, Integer> map = new HashMap<>();
map.put(a, 10);
map.put(b, 20);
System.out.println(map.size()); // 1
System.out.println(map.get("id-42")); // 20
~~~

`intern` chỉ trả về tham chiếu chuẩn trong string pool; nếu sau `intern` ta so sánh bằng `==` thì đang kiểm tra identity của **những tham chiếu đã intern**, chứ không thay đổi hợp đồng của `HashMap` hay `HashSet`. Hai nội dung khác nhau vẫn khác nhau; hai nội dung bằng nhau vẫn bằng nhau kể cả trước khi intern. Nếu cần bản đồ dùng **identity** thật sự, phải lựa chọn cấu trúc đặc biệt như `IdentityHashMap`, vốn có ngữ nghĩa khác `HashMap` (phần 6).

**Hash collision là vấn đề riêng**: `"Aa".hashCode() == "BB".hashCode()` nhưng `"Aa".equals("BB")` là `false`. Không so hai nội dung chỉ bằng hash; chi tiết hợp đồng được trình bày trong bài về va chạm băm.

## 5. Ví dụ Java 17+ hoàn chỉnh, có thể chạy

Lưu chương trình dưới tên `StringCollectionEqualityDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class StringCollectionEqualityDemo {
    public static void main(String[] args) {
        String pooled = "java";
        String separate = new String("java");
        String rebuilt = new StringBuilder()
                .append("ja")
                .append("va")
                .toString();

        System.out.println("referenceEquals=" + (pooled == separate));
        System.out.println("valueEquals=" + pooled.equals(separate));
        System.out.println("internEquals=" +
                (pooled == separate.intern()));
        System.out.println("sameHash=" +
                (pooled.hashCode() == separate.hashCode()));

        Set<String> tags = new HashSet<>();
        tags.add(pooled);
        tags.add(separate);
        tags.add(rebuilt);

        System.out.println("hashSetSize=" + tags.size());
        System.out.println("hashSetContains=" +
                tags.contains(new String("java")));

        Map<String, Integer> scores = new HashMap<>();
        scores.put(new String("id-42"), 10);
        scores.put("id-42", 20);

        System.out.println("hashMapSize=" + scores.size());
        System.out.println("hashMapValue=" +
                scores.get(new String("id-42")));

        // Trường hợp chủ ý dùng identity thay vì content.
        Set<String> identities = Collections.newSetFromMap(
                new IdentityHashMap<String, Boolean>()
        );
        identities.add(new String("key"));
        identities.add(new String("key"));
        System.out.println("identitySetSize=" + identities.size());

        // Sorted Set có thể dựa trên Comparator.
        Set<String> sorted = new TreeSet<>(
                String.CASE_INSENSITIVE_ORDER
        );
        sorted.add("Lan");
        sorted.add("lan");
        System.out.println("treeSetSize=" + sorted.size());
        System.out.println("treeSetContains=" +
                sorted.contains("LAN"));

        System.out.println("equalsIgnoreCase=" +
                "Java".equalsIgnoreCase("JAVA"));
        System.out.println("nullSafe=" +
                Objects.equals(null, null));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("differentFormsEquals=" +
                composed.equals(decomposed));
        System.out.println("normalizedEquals=" +
                composed.equals(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));

        System.out.println("collisionHashes=" +
                ("Aa".hashCode() == "BB".hashCode()));
        System.out.println("collisionEquals=" +
                "Aa".equals("BB"));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên (lưu tệp bằng UTF-8):

~~~bash
javac -encoding UTF-8 StringCollectionEqualityDemo.java
java StringCollectionEqualityDemo
~~~

`stdout`:

~~~text
referenceEquals=false
valueEquals=true
internEquals=true
sameHash=true
hashSetSize=1
hashSetContains=true
hashMapSize=1
hashMapValue=20
identitySetSize=2
treeSetSize=1
treeSetContains=true
equalsIgnoreCase=true
nullSafe=true
differentFormsEquals=false
normalizedEquals=true
collisionHashes=true
collisionEquals=false
~~~

Giải thích kết quả quan trọng:

1. Ba chuỗi `pooled`, `separate`, `rebuilt` có cùng nội dung `java`; `==` chỉ phản ánh định danh, còn `equals` phản ánh giá trị.
2. `HashSet` chỉ lưu một phần tử; `HashMap` chỉ lưu một entry và giá trị cuối là `20`, dù các đối tượng khóa được tạo riêng.
3. `IdentityHashMap` cố ý dùng **`==`** để phân biệt các khóa. Hai đối tượng `new String("key")` khác nhau làm số phần tử trong set được xây từ identity map là **2**. Đây là hành vi theo thiết kế của collection đặc biệt này.
4. `TreeSet` dùng `String.CASE_INSENSITIVE_ORDER` nên coi `"Lan"` và `"lan"` tương đương theo comparator, dù `"Lan".equals("lan")` là `false`.
5. Hai cách biểu diễn chữ `é` không `equals` trước khi chuẩn hóa; chuẩn hóa `NFC` đưa chúng về cùng dạng.
6. Hai chuỗi `Aa` và `BB` cho cùng hash code, nhưng nội dung không giống nhau, minh họa lý do vẫn phải xét `equals`.

## 6. Ngoại lệ quan trọng: không phải collection nào cũng dùng `String.equals()`

### 6.1. `IdentityHashMap` dùng định danh đối tượng

`IdentityHashMap` được thiết kế để coi hai khóa là bằng nhau khi chúng cùng tham chiếu đến **một đối tượng**. Đó là cấu trúc phù hợp cho một số bài toán theo dõi đối tượng hoặc đồ thị định danh, nhưng **không phù hợp** nếu nghiệp vụ cần nhóm các khóa `String` theo nội dung.

Ví dụ:

~~~java
IdentityHashMap<String, Integer> map = new IdentityHashMap<>();
map.put(new String("user"), 1);
map.put(new String("user"), 2);

System.out.println(map.size()); // 2
~~~

Dùng `intern()` để làm cho `IdentityHashMap` hoạt động giống `HashMap` là cách thiết kế sai hướng: ta đã chọn một collection có **quan hệ bằng nhau khác**, sau đó cố can thiệp tham chiếu để ép nó cho kết quả mong muốn. Hãy chọn `HashMap` nếu cần content equality.

### 6.2. `TreeSet` và `TreeMap` dùng thứ tự so sánh

Các collection có sắp xếp dùng `Comparator.compare(a, b) == 0` hoặc `Comparable.compareTo` trả về `0` để quyết định hai khóa có tương đương trong tập thứ tự hay không.

Với thứ tự tự nhiên của `String`, `a.compareTo(b) == 0` có quan hệ nhất quán với `a.equals(b)`. Tuy nhiên, khi truyền một comparator không phân biệt chữ hoa/chữ thường:

~~~java
Set<String> names = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
names.add("Admin");
names.add("admin");

System.out.println(names.size()); // 1
System.out.println("Admin".equals("admin")); // false
~~~

Ở đây, `TreeSet` gom hai chuỗi theo **comparator**, khác với `HashSet` phân biệt chúng theo `equals/hashCode`. `String.CASE_INSENSITIVE_ORDER` không nhất quán với `String.equals` đối với những chuỗi khác nhau chỉ ở chữ hoa/thường; vì vậy cần cân nhắc hợp đồng `Set` khi chọn comparator và không giả định hai loại tập có cùng quy tắc trùng lặp.

Nếu hệ thống yêu cầu so sánh khóa không phân biệt chữ hoa/thường, nên xác định chiến lược nhất quán toàn hệ thống (ví dụ chuẩn hóa khóa trước khi đưa vào hash collection) và hiểu các quy tắc Unicode/locale liên quan.

## 7. `intern` không thay cho chuẩn hóa nội dung

`intern` **không** đổi chữ hoa/thường, bỏ khoảng trắng hay ghép Unicode về NFC. Do đó, hai giá trị `"Java"` và `"java"`, hoặc `"\u00E9"` với `"e\u0301"`, vẫn có thể là hai giá trị khác nhau dù mỗi bên đã `intern`. String pool gom tham chiếu khi **nội dung đã bằng nhau**, không biến nhiều cách viết thành một định danh nghiệp vụ.

Nếu sản phẩm muốn các cách viết được coi là một key, phải định nghĩa một hàm canonicalization phù hợp và dùng nó ở cả thao tác lưu/tìm; việc bảo toàn nhãn gốc cho hiển thị là trách nhiệm khác. `equalsIgnoreCase` cũng không làm `HashMap` tự đổi hợp đồng khóa. Bài chuyên về chuẩn hóa khóa trình bày chính sách, Unicode normalization và xử lý các biến thể va chạm.

## 8. `null` và chọn chiều gọi `equals()`

Khi giá trị có thể `null`, lời gọi như sau không an toàn:

~~~java
String input = null;
// input.equals("ok"); // Ném NullPointerException.
~~~

Các cách so sánh an toàn:

~~~java
import java.util.Objects;

String input = null;
System.out.println("ok".equals(input));       // false
System.out.println(Objects.equals(input, "ok")); // false
System.out.println(Objects.equals(null, null));  // true
~~~

`Objects.equals(a, b)` kiểm tra đồng nhất tham chiếu hoặc `equals` theo cách null-safe: hai giá trị `null` được coi là bằng nhau; một giá trị `null` còn giá trị kia không `null` là không bằng nhau.

`HashMap` và `HashSet` của Java cho phép `null` theo quy tắc riêng của chúng, nhưng điều đó không có nghĩa rằng ta có thể gọi phương thức `equals()` trên tham chiếu `null`. Đây là hai vấn đề khác nhau.

## 9. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `if (input == "admin")` để xét nội dung | Dữ liệu tạo ở runtime có thể bị nhận diện sai | `"admin".equals(input)` |
| Dùng `intern()` trước mọi thao tác `HashMap` | Thêm xử lý pool không cần cho content equality | Tin vào `String.equals/hashCode` và chọn collection đúng |
| So sánh chỉ bằng `hashCode()` | Hash collision gây kết luận bằng nhau sai | Dùng `equals()` |
| Dùng `IdentityHashMap` cho khóa chuỗi nghiệp vụ | Hai đối tượng cùng nội dung có thể thành hai khóa | Dùng `HashMap` |
| Nghĩ `HashSet` và `TreeSet` luôn xử lý trùng giống nhau | `TreeSet` có thể dùng comparator quy định quan hệ khác | Chọn và kiểm tra comparator rõ ràng |
| Nghĩ `equals` tự trim, không phân biệt hoa/thường, chuẩn hóa Unicode | Những khác biệt này được giữ nguyên | Chuẩn hóa theo yêu cầu nghiệp vụ trước khi lưu/tra |
| Gọi `nullable.equals(other)` | Có thể ném `NullPointerException` | `Objects.equals(nullable, other)` hoặc gọi `equals` trên literal |
| Dựa vào kết quả `==` của hai string literal để suy ra mọi chuỗi cùng nội dung là cùng đối tượng | Code chỉ đúng ngẫu nhiên do pooling | Dùng `equals` ở mọi nguồn dữ liệu |

### Checklist khi dùng `String` làm khóa collection

- Mục tiêu là **content equality** hay **reference identity**?
- Nếu là content equality, collection đã dùng `equals/hashCode` đúng chưa?
- Quy tắc phân biệt chữ hoa/thường, khoảng trắng, Unicode normalization đã được định nghĩa chưa?
- Input từ nhiều nguồn có được chuẩn hóa **cùng cách** trước khi `put`, `add`, `get`, `contains` không?
- Nếu dùng `TreeMap`/`TreeSet`, comparator có quan hệ bằng nhau mong muốn không?
- Các chuỗi nullable có được xử lý an toàn không?
- Test có dùng `new String(...)` hoặc chuỗi tạo lúc runtime để tránh phụ thuộc vô tình vào intern pool không?

**Kết luận:** Với `String` trong `HashSet`, `HashMap` và đa số tình huống so sánh giá trị, **hãy so sánh bằng `equals()`** và dựa vào `hashCode()` được cài đặt sẵn. `intern()` quản lý đối tượng đại diện trong string pool, không phải điều kiện để biết hai chuỗi có cùng nội dung. Dùng `==` chỉ khi thực sự cần **định danh tham chiếu**, và kiểm tra quy tắc comparator nếu collection có thứ tự.
