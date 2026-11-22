# Phân biệt diamond (`<>`) với kiểu thô (raw type) trong Java

## Mục tiêu học tập

**Diamond** là cặp dấu `<>` trong biểu thức tạo đối tượng generic, chẳng hạn `new ArrayList<>()`. Nó giúp **compiler suy luận đối số kiểu** mà không phải viết lại `String`, `Integer` hoặc các kiểu generic dài ở phía sau `new`. Cú pháp này được bổ sung từ **Java 7** và vẫn được dùng rộng rãi trong Java hiện đại.

**Raw type** là cách dùng tên một kiểu generic **không có đối số kiểu**, chẳng hạn `List` thay vì `List<String>`, hoặc `new ArrayList()` thay vì `new ArrayList<>()`. Java vẫn cho phép raw type vì tương thích mã và API cũ, nhưng JLS hiện hành **khuyến cáo mạnh không dùng raw type trong mã mới** vì nó làm suy yếu kiểm tra kiểu khi biên dịch.

Sau bài này, bạn cần:

- Nhận diện chính xác đâu là generic có tham số kiểu, đâu là diamond, đâu là raw type.
- Giải thích vì sao `new ArrayList<>()` không tương đương với `new ArrayList()` dù cả hai đều tạo `ArrayList`.
- Hiểu cách compiler suy luận kiểu từ ngữ cảnh và giới hạn của việc suy luận.
- Hiểu `rawtypes`, `unchecked`, **heap pollution** và nguyên nhân `ClassCastException` có thể xuất hiện khi đọc danh sách.
- Chọn cách khai báo và chuyển đổi an toàn trong code Java 17+; dùng `List<?>` khi chưa biết loại phần tử, thay vì lạm dụng raw type.

**Bối cảnh phiên bản:** Generics đã có từ Java 5; diamond được thêm ở Java 7. Những nguyên tắc type safety, raw type và suy luận kiểu dưới đây vẫn áp dụng ở Java hiện đại. Các ví dụ biên dịch bằng Java 17; nếu có cú pháp từ phiên bản sau Java 7, bài sẽ nói rõ.

## 1. Nhìn vào dấu ngoặc để phân biệt

Cùng mục đích tạo một danh sách chuỗi, các cách viết dưới đây **không tương đương về mức độ an toàn kiểu**:

~~~java
List<String> a = new ArrayList<String>(); // Generic, chỉ rõ kiểu ở hai phía
List<String> b = new ArrayList<>();       // Generic + diamond, compiler suy luận String
List<String> c = new ArrayList();         // Raw constructor, unchecked conversion
List d = new ArrayList();                 // Raw ở cả hai phía
List e = new ArrayList<>();               // Phía trái vẫn raw, không an toàn kiểu
~~~

Đây là **những dòng minh họa**, đặt trong một class/method đã import `java.util.List` và `java.util.ArrayList`. Ví dụ `c`, `d`, `e` được đưa ra **để nhận diện và sửa code**, không phải phong cách nên áp dụng.

| Cách khai báo | Compiler biết phần tử ở biến đích? | Có raw type? | Hậu quả |
| --- | --- | --- | --- |
| `List<String> x = new ArrayList<String>();` | Có, `String` | Không | An toàn kiểu, nhưng lặp lại đối số kiểu |
| `List<String> x = new ArrayList<>();` | Có, `String` | Không | Cách viết gọn, thường nên dùng |
| `List<String> x = new ArrayList();` | Biến `x` mang kiểu `String`, nhưng phép chuyển từ raw **unchecked** | Có ở biểu thức tạo đối tượng | Compiler không chứng minh được tính an toàn khi chuyển kiểu |
| `List x = new ArrayList();` | Không, truy xuất qua `x` mất thông tin kiểu phần tử | Có | Dễ trộn các loại phần tử, có cảnh báo khi thao tác không an toàn |
| `List x = new ArrayList<>();` | **Không**: biến `x` vẫn là `List` raw | Có ở kiểu biến đích | Diamond ở `new` không sửa được khai báo raw |

**Quy tắc đọc nhanh:** `<String>` là **đối số kiểu cụ thể**; `<>` là **yêu cầu suy luận đối số kiểu khi tạo đối tượng**; bỏ hẳn dấu `<...>` ở một vị trí đáng lẽ là generic có thể tạo **raw type**.

Cần phân biệt `List` với các kiểu **không khai báo generic** như `String`: `String` không có `<T>`, vì thế bản thân tên `String` **không phải** raw type. Và diamond phải gắn với một **class generic có thể khởi tạo**, không dùng `new List<>()` vì `List` là interface.

## 2. Diamond hoạt động thế nào ở thời điểm biên dịch?

### 2.1. Compiler suy luận kiểu, không “để trống kiểu”

Ví dụ:

~~~java
Map<String, List<Integer>> scores = new HashMap<>();
~~~

Ở bên trái, kiểu kỳ vọng là `Map<String, List<Integer>>`. Với biểu thức `new HashMap<>()`, compiler có thể suy luận các đối số kiểu của class `HashMap<K,V>` là `String` và `List<Integer>`. Điều đó tương đương về kiểm tra kiểu với cách viết đầy đủ:

~~~java
Map<String, List<Integer>> scores =
        new HashMap<String, List<Integer>>();
~~~

Nếu viết thiếu diamond:

~~~java
Map<String, List<Integer>> scores = new HashMap();
~~~

thì `HashMap()` là **lệnh tạo raw type**; phép gán sang kiểu có tham số cần `unchecked conversion` và compiler phải cảnh báo. **Kiểu ở vế trái không biến raw constructor thành generic constructor.**

JLS §15.9 quy định cú pháp `<>` khiến **các đối số kiểu của class được suy luận**. Compiler căn cứ vào biểu thức khởi tạo, đối số constructor và ngữ cảnh mong đợi, không dựa vào dữ liệu ngẫu nhiên được thêm vào danh sách về sau.

### 2.2. Các ngữ cảnh suy luận thường gặp

~~~java
List<String> names = new ArrayList<>();     // Kiểu đích của phép gán
List<Integer> emptyNumbers = new ArrayList<>();

// Trong lời gọi method có tham số List<String>:
// useNames(new ArrayList<>());

// Trong phương thức khai báo trả về List<String>:
// return new ArrayList<>();
~~~

Hai dòng có chú thích `useNames` và `return` là **minh họa ngữ cảnh**, không phải lệnh chạy độc lập. Compiler có thể sử dụng kiểu của tham số hoặc kiểu trả về mong đợi để giải bài toán suy luận. Không được hiểu rằng compiler nhìn các câu `add(...)` viết sau đó để “sửa lại” generic type đã suy ra.

### 2.3. Khi không có kiểu đích đủ cụ thể

Trong Java 10+, `var` suy luận kiểu của **biến cục bộ** từ biểu thức khởi tạo. Cẩn thận với cách viết:

~~~java
var values = new ArrayList<>(); // Suy luận ArrayList<Object>
values.add("text");            // Hợp lệ
values.add(123);               // Cũng hợp lệ
~~~

Đây là **đoạn mã dùng Java 10+**, không phải cú pháp Java 7. Vì không có `List<String>` ở phía trái và constructor không đưa ra ràng buộc kiểu cụ thể, kết quả suy luận là `ArrayList<Object>`. Code **không trở thành raw type**, nhưng cũng **không bảo đảm chỉ chứa chuỗi**.

Nếu mục tiêu là danh sách chỉ chứa chuỗi, hãy viết rõ:

~~~java
List<String> values = new ArrayList<>();
// hoặc, với Java 10+:
var values2 = new ArrayList<String>();
~~~

Điều cần nhớ: **diamond có thể suy luận `Object` khi thiếu ràng buộc**. Vì vậy, “có `<>`” không đồng nghĩa compiler đã suy ra đúng một kiểu domain mà lập trình viên mong muốn.

## 3. Chương trình an toàn: generic kết hợp diamond

Lưu thành `DiamondSafetyDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DiamondSafetyDemo {
    static int count(List<String> names) {
        return names.size();
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add("Mai");

        Map<String, List<Integer>> scores = new HashMap<>();
        scores.put("team", new ArrayList<>(List.of(10, 20)));

        System.out.println("first=" + names.get(0));
        System.out.println("count=" + count(new ArrayList<>(names)));
        int sum = scores.get("team").stream()
                .mapToInt(Integer::intValue).sum();
        System.out.println("sum=" + sum);
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 DiamondSafetyDemo.java
java DiamondSafetyDemo
~~~

Stdout:

~~~text
first=Lan
count=2
sum=30
~~~

Giải thích:

1. `new ArrayList<>()` của `names` suy luận `String` từ `List<String>`. Lệnh `names.add(123)` (nếu thêm vào) sẽ bị từ chối **lúc biên dịch**.
2. `new HashMap<>()` suy luận hai đối số kiểu, dù giá trị là một generic lồng nhau `List<Integer>`.
3. `new ArrayList<>(List.of(10, 20))` tạo danh sách `Integer`. `List.of` là API có từ Java 9 và **được dùng ở đây vì ví dụ nhắm Java 17+**; nó không phải một phần của tính năng diamond ban đầu.
4. `count(new ArrayList<>(names))` minh họa biểu thức generic `new` được suy luận khi làm đối số của phương thức nhận `List<String>`.
5. `Integer::intValue` cùng `sum()` tạo tổng 30. Ví dụ này dùng API và cú pháp hiện hành; điểm cốt lõi của bài là **type safety và cú pháp `<>`**, không phải Stream API.

Khác với raw type, đối với `names` compiler biết phép gọi `get(0)` có kiểu kết quả là `String`, nên không cần ép kiểu thủ công khi dùng.

## 4. Raw type làm mất những bảo đảm nào?

### 4.1. Raw type vẫn hợp lệ cú pháp, nhưng không phải lựa chọn cho code mới

Ví dụ:

~~~java
List raw = new ArrayList();
raw.add("Lan");
raw.add(123);
~~~

Đây là **đoạn mã để nhận diện lỗi**, không phải gợi ý thiết kế. `List` và `ArrayList` ở đây là raw, nên compiler không thể bảo đảm tất cả phần tử tuân thủ một đối số kiểu như `String`. Lời gọi `raw.add(...)` liên quan phương thức generic sau khi bị erasure và phát sinh **unchecked warning**; nếu bật `-Xlint:rawtypes`, kiểu `List`/`ArrayList` viết raw cũng được cảnh báo.

Raw type tồn tại để mã nguồn có thể tương tác với API cũ; chuẩn Java hiện hành vẫn mô tả cơ chế này nhưng **khuyến cáo mạnh tránh raw type trong mã mới**. Không nên tắt cảnh báo hàng loạt để tiếp tục viết raw.

### 4.2. `unchecked` khác với lỗi biên dịch

Hai ví dụ:

~~~java
List<String> good = new ArrayList<>(); // Không cần unchecked conversion
List<String> risky = new ArrayList();  // Biên dịch nhưng có unchecked warning
~~~

Với dòng thứ hai, compiler không chứng minh được đối tượng lấy từ kiểu raw thực sự tuân theo `List<String>`. Vì mục tiêu tương thích, ngôn ngữ cho phép phép chuyển đó **kèm cảnh báo**. Cảnh báo không phải giấy chứng nhận an toàn; nó báo rằng hệ thống kiểu tĩnh không thể kiểm tra đầy đủ rủi ro.

Ngược lại, code đã khai báo generic đúng sẽ bị chặn ngay khi thêm phần tử sai kiểu:

~~~java
List<String> names = new ArrayList<>();
names.add(42); // LỖI BIÊN DỊCH: int/Integer không thể dùng làm String
~~~

Đây là **ví dụ cố ý không biên dịch**. Sửa bằng cách chỉ thêm `String`, hoặc thay đổi thiết kế kiểu dữ liệu một cách có chủ đích; không xóa đối số kiểu để “qua compiler”.

### 4.3. Heap pollution và `ClassCastException` xảy ra muộn

*Heap pollution* là tình huống biến được khai báo có kiểu có tham số (chẳng hạn `List<String>`) thực tế tham chiếu tới một đối tượng có phần tử không thỏa mãn kiểu đó. Nó có thể xảy ra do raw type, phép chuyển không kiểm tra hoặc một số thao tác không an toàn khác. Một bug nguy hiểm là đoạn code **ghi dữ liệu sai kiểu không nổ ngay**, nhưng code **đọc theo kiểu đã khai báo** mới gặp exception.

Chương trình hoàn chỉnh `RawTypePitfallDemo.java` (để quan sát tác hại của raw type):

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawTypePitfallDemo {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("Lan");
        raw.add(123);

        List<String> names = raw; // Unchecked conversion
        System.out.println("size=" + names.size());

        try {
            for (String name : names) {
                System.out.println(name.toUpperCase());
            }
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
~~~

Chạy để xem cảnh báo khi biên dịch và hậu quả lúc runtime:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked RawTypePitfallDemo.java
java RawTypePitfallDemo
~~~

Stdout của **lệnh `java`**:

~~~text
size=2
LAN
ClassCastException
~~~

Lệnh `javac` phát cảnh báo `rawtypes` và `unchecked` ở các vị trí liên quan; văn bản và số lượng cảnh báo có thể khác nhau theo compiler, vì vậy không đưa diagnostics của compiler vào bảng stdout cố định.

**Cơ chế:** `raw.add(123)` cho phép một `Integer` lẫn vào danh sách. `List<String> names = raw` thực hiện phép chuyển không kiểm tra. Khi vòng lặp `for (String name : names)` lấy phần tử thứ hai, compiler đã tạo kiểm tra/ép kiểu tương ứng với `String`; giá trị thật là `Integer`, gây `ClassCastException`. Việc `size()` trả về 2 không chứng minh hai phần tử đều là `String`.

Đây là lý do compiler yêu cầu kiểm tra cảnh báo: vùng phát sinh lỗi dữ liệu có thể nằm ở một nơi, còn exception xuất hiện ở nơi rất xa.

## 5. Diamond không thay thế generic type của biến

Dễ nhầm nhất là nghĩ thêm `<>` ở vế phải đủ để loại raw:

~~~java
List words = new ArrayList<>();
words.add("one");
words.add(2);                   // Phép gọi qua biến raw: unchecked warning
~~~

**Biến `words` vẫn có kiểu raw `List`**, vì phía trái không ghi `<String>`. Compiler không thể dùng diamond ở phía phải để biến một khai báo raw thành `List<String>`.

Cách sửa đúng:

~~~java
List<String> words = new ArrayList<>();
words.add("one");
// words.add(2);                // Sẽ bị compiler từ chối
~~~

Ở chiều ngược lại cũng không được bỏ diamond và chỉ hy vọng kiểu ở vế trái đủ an toàn:

~~~java
List<String> words = new ArrayList(); // Unchecked warning
~~~

**Luôn rà soát cả hai vế**: kiểu biến/tham số/giá trị trả về cần thể hiện generic phù hợp, và biểu thức khởi tạo nên dùng diamond hoặc đối số kiểu tường minh.

### 5.1. Không nhầm với `List<Object>` và `List<?>`

| Kiểu | Ý nghĩa | Có thể thêm `String` qua biến đó? | Lấy ra dưới dạng gì? |
| --- | --- | --- | --- |
| `List<String>` | Các phần tử được kiểm tra theo `String` | Có | `String` |
| `List<Object>` | Danh sách chứa giá trị kiểu `Object` | Có | `Object` |
| `List<?>` | Danh sách có kiểu phần tử **chưa biết** | Không, trừ `null` | `Object` |
| `List` raw | Bỏ kiểm tra tham số kiểu ở nhiều thao tác | Có thể, thường có unchecked warning | `Object` |

Điểm quan trọng:

- `List<?>` là **parameterized type với wildcard**, **không phải raw type**. Đây là lựa chọn an toàn để **đọc/duyệt** danh sách không biết loại phần tử.
- `List<Object>` và `List<String>` không hoán đổi cho nhau tùy ý: generic Java thường **invariant**. Không thể coi một `List<String>` là `List<Object>` để rồi thêm một `Integer`.
- `List<?>` hạn chế thêm phần tử không phải vì thiếu tính năng, mà vì compiler **không biết kiểu cụ thể nào** được phép thêm; điều đó ngăn nhiều kiểu sai nguy hiểm.
- Sử dụng `Object` hay `?` phải bám hợp đồng thật của API. Nếu thực tế là `List<String>`, viết đúng `List<String>`, đừng dùng wildcard chỉ để né việc khai báo kiểu.

## 6. Cách thay raw type an toàn khi nhận dữ liệu không đáng tin về kiểu

Nếu API hiện hành của bạn có thể thay đổi, **hãy đưa generic type vào chữ ký**:

~~~java
// Nên thiết kế theo kiểu cụ thể nếu nghiệp vụ bảo đảm phần tử là String:
static List<String> loadNames() {
    return new ArrayList<>();
}
~~~

Đây là **phương thức minh họa đặt trong một class** đã import `List` và `ArrayList`.

Khi phải tiếp nhận một danh sách mà **không có hợp đồng về kiểu phần tử**, hãy công khai sự chưa biết bằng `List<?>` và kiểm tra từng giá trị trước khi tạo bản sao có kiểu.

Tạo tệp `ValidatedCopyDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ValidatedCopyDemo {
    static List<String> checkedStrings(List<?> source) {
        List<String> result = new ArrayList<>();
        for (Object element : source) {
            if (!(element instanceof String text)) {
                throw new IllegalArgumentException("Expected String");
            }
            result.add(text);
        }
        return result;
    }

    public static void main(String[] args) {
        List<?> ok = List.of("java", "diamond");
        System.out.println(checkedStrings(ok));

        List<?> mixed = List.of("java", 7);
        try {
            System.out.println(checkedStrings(mixed));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 ValidatedCopyDemo.java
java ValidatedCopyDemo
~~~

Stdout:

~~~text
[java, diamond]
Expected String
~~~

Giải thích:

1. `List<?>` là kiểu được compiler kiểm soát; vòng lặp đọc mỗi phần tử dưới dạng `Object`, không lén giả định là `String`.
2. `instanceof String text` kiểm tra và tạo biến `text` kiểu `String` khi điều kiện hợp lệ. Đây là **pattern matching for instanceof**, tính năng ổn định từ **Java 16**, dùng được trong Java 17+.
3. Chỉ những phần tử đã qua kiểm tra mới được thêm vào `List<String> result = new ArrayList<>()`. Diamond giữ type safety tại đây.
4. Dữ liệu hỗn hợp bị phát hiện tại **ranh giới kiểm tra**, với `IllegalArgumentException` có chủ đích, thay vì dẫn tới một `ClassCastException` khó lần vết ở vị trí đọc sau này.
5. `List.of` là API Java 9+; nó được dùng để tạo input ngắn cho ví dụ Java 17+, không được gán là cú pháp Java 7.

Với một API raw do bên thứ ba cung cấp, có thể tiếp nhận kết quả vào `List<?>` rồi kiểm tra dữ liệu theo cách trên. Đừng lập tức ép sang `List<String>` và dùng `@SuppressWarnings("unchecked")`: annotation chỉ **ẩn cảnh báo**, không kiểm tra nội dung phần tử. Việc ép kiểu có kiểm tra không đầy đủ chỉ nên nằm trong một lớp chuyển tiếp được kiểm soát, có bằng chứng về bất biến kiểu và kiểm thử tương ứng.

**Giới hạn quan trọng:** Việc tạo `new ArrayList<>(rawCollection)` hoặc ép `(List<String>) rawList` không tự động xác thực rằng các phần tử đều là `String`. Nếu nguồn có thể chứa nhiều kiểu, cần kiểm tra từng phần tử, hoặc thay đổi API nguồn để công khai kiểu đúng.

## 7. Diamond và type erasure: vì sao runtime trông giống nhau?

Generic types của Java chủ yếu được kiểm tra tại **thời điểm biên dịch** và nhiều thông tin đối số kiểu bị xóa khỏi kiểu runtime (*type erasure*). Vì vậy:

~~~java
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
System.out.println(a.getClass() == b.getClass()); // true
~~~

Đây là **đoạn mã minh họa** bên trong phương thức đã import `List` và `ArrayList`. Cả hai đều là các đối tượng `ArrayList` ở runtime. Điều này **không khiến diamond tương đương raw type**: compiler đã kiểm tra `a.add(...)` theo `String` và `b.add(...)` theo `Integer` trước khi chạy.

Vì erasure, không thể kiểm tra kiểu phần tử của cả một danh sách bằng `instanceof List<String>`. Muốn xác minh dữ liệu không có hợp đồng kiểu, cần kiểm tra phần tử cụ thể hoặc dùng schema/decoder thích hợp. Generic compile-time safety và runtime input validation giải quyết **hai tầng vấn đề khác nhau**, đều cần thiết.

## 8. Những lỗi và hiểu nhầm thường gặp

1. **“Bỏ đối số kiểu cũng là cách suy luận”:** sai. `new ArrayList()` là raw; `new ArrayList<>()` mới kích hoạt diamond.
2. **“Vế trái `List<String>` sẽ làm raw constructor an toàn”:** sai. `List<String> x = new ArrayList();` vẫn có unchecked conversion.
3. **“Chỉ cần thêm diamond ở vế phải”:** sai. `List x = new ArrayList<>();` vẫn có biến raw ở vế trái.
4. **“Diamond luôn suy ra kiểu mình muốn”:** sai. Nếu thiếu ràng buộc, ví dụ `var x = new ArrayList<>()` trên Java 10+, kiểu phần tử có thể là `Object`.
5. **“Compiler cảnh báo nhưng ứng dụng chạy được thì ổn”:** không có bảo đảm đó. Raw/unchecked có thể tạo heap pollution và gây `ClassCastException` tại vị trí đọc.
6. **“Generics chỉ là cú pháp, vì runtime đều là ArrayList”:** sai. Kiểm tra kiểu ở compile time là tác dụng quan trọng giúp chặn bug trước khi chạy.
7. **“`List<?>` là raw”:** sai. Wildcard là một tham số kiểu hợp lệ và giới hạn thao tác ghi không an toàn.
8. **“`List<Object>` nhận được `List<String>`”:** sai trong hệ thống generic thông thường vì invariance.
9. **“`@SuppressWarnings` sửa được dữ liệu hỗn hợp”:** sai. Nó chỉ điều khiển cảnh báo; cần ràng buộc API, đối tượng chuyển đổi có kiểm tra và kiểm thử.
10. **“Có thể viết `new List<>()`”:** sai vì `List` là interface. Hãy khởi tạo class cụ thể như `new ArrayList<>()`.
11. **“Diamond áp dụng cho mọi dấu ngoặc generic”:** sai. Diamond là cú pháp **trong biểu thức tạo instance generic**, không viết `List<> names` khi khai báo biến.
12. **“Mọi biến thể diamond hiện có đều từ Java 7”:** sai. Chẳng hạn khả năng dùng diamond với anonymous class được mở rộng ở Java 9; khi code cần tương thích Java 7 phải kiểm tra đúng phiên bản ngôn ngữ. Với dự án Java 17+, cách khởi tạo generic thông thường như trong bài là ổn định.

## 9. Checklist khi đọc hoặc sửa code

Khi thấy `List`, `Map`, `Set`, `Optional`, `Comparable` hoặc một class generic tự viết:

1. **Xem khai báo biến, tham số và kiểu trả về:** có thể dùng đối số kiểu rõ ràng như `List<String>`, `Map<String, Integer>` không?
2. **Xem câu lệnh `new`:** đã dùng `<>` hoặc đối số kiểu tường minh, hay đang tạo raw?
3. **Kiểm tra output compiler:** bật `javac -Xlint:rawtypes,unchecked` (hoặc cấu hình cảnh báo tương đương trong build) để tìm những chỗ mất kiểm tra kiểu.
4. **Xem nguồn dữ liệu:** nếu nguồn trả raw hoặc dữ liệu hỗn hợp, có bản sao đã kiểm tra từng phần tử trước khi đưa vào collection có kiểu không?
5. **Phân biệt unknown và Object:** dữ liệu chưa biết kiểu nên thường đi qua `List<?>`; danh sách thực sự chứa nhiều loại theo thiết kế mới cân nhắc `List<Object>`.
6. **Giữ tương thích phiên bản:** các ví dụ `var`, `List.of`, `instanceof String s` cần Java 10, 9, 16 tương ứng; tính năng diamond cơ bản đã có từ Java 7.

## 10. Bài tự kiểm tra

**Câu 1.** `List<String> a = new ArrayList();` có lỗi biên dịch không?  
**Đáp án:** Thông thường **vẫn biên dịch**, nhưng có `unchecked conversion` warning. Dùng `new ArrayList<>()` để giữ type safety.

**Câu 2.** `List b = new ArrayList<>();` có biến `b` kiểu `List<String>` không?  
**Đáp án:** **Không.** `b` là raw `List`, vì phía trái không có đối số kiểu. Diamond ở phía phải không khôi phục thông tin kiểu cho biến.

**Câu 3.** `var c = new ArrayList<>();` ở Java 17 có mặc định là `ArrayList<String>` không?  
**Đáp án:** **Không.** Không có ràng buộc cụ thể nên compiler suy luận `ArrayList<Object>`.

**Câu 4.** `List<String> a = new ArrayList<>(); a.add(5);` chạy rồi mới ném `ClassCastException`?  
**Đáp án:** **Không.** Đây là lỗi **compile-time**; `add` yêu cầu `String`.

**Câu 5.** Vì sao ví dụ raw type đọc phần tử có thể lỗi dù `size()` trả bình thường?  
**Đáp án:** Kích thước danh sách không kiểm tra kiểu từng phần tử. Chỉ khi chương trình cần lấy một `Integer` dưới dạng `String` thì thao tác ép kiểu runtime mới thất bại.

**Câu 6.** Nếu nhận `List` từ API chưa xác minh kiểu phần tử, nên ép thẳng `(List<String>)` hay duyệt `List<?>` để xác thực?  
**Đáp án:** Ưu tiên nhận dưới `List<?>`, kiểm tra từng phần tử rồi tạo `List<String>` mới. Chỉ ép kiểu không kiểm tra nếu thực sự có bất biến kiểu được bảo đảm và kiểm soát.

## Tài liệu chính thức

- [Oracle Java SE 7 — Java Programming Language Enhancements](https://docs.oracle.com/javase/7/docs/technotes/guides/language/enhancements.html): nguồn gốc diamond ở Java 7, dùng để xác nhận mốc phát hành.
- [JLS Java SE 25 §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9): hợp đồng hiện hành cho `new GenericClass<>()` và suy luận đối số kiểu.
- [JLS Java SE 25 §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5): đối số kiểu, wildcard và các quy tắc kiểu generic.
- [JLS Java SE 25 §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.8): định nghĩa raw type, cảnh báo và lý do tương thích mã cũ.
- [JLS Java SE 25 §5.1.9 — Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.9): vì sao phép chuyển từ raw sang generic có cảnh báo.
- [JLS Java SE 25 §4.12.2 — Variables of Reference Type](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.2): nguy cơ heap pollution khi biến có tham số kiểu nhận dữ liệu không thỏa hợp đồng.
- [Oracle — Type Inference for Generic Instance Creation](https://docs.oracle.com/javase/8/docs/technotes/guides/language/type-inference-generic-instance-creation.html): ví dụ chính thống về `new HashMap<>()` so với raw `new HashMap()`; tài liệu dùng làm **bằng chứng giải thích cú pháp**, còn JLS hiện hành là nguồn quyết định ngữ nghĩa.
- [Oracle — Java Tutorials, Raw Types](https://docs.oracle.com/javase/tutorial/java/generics/rawTypes.html): ví dụ tương tác với raw types và unchecked conversion, dùng để hiểu tác hại raw type chứ không làm mẫu thiết kế mới.

**Ghi nhớ:** `<>` **yêu cầu compiler suy luận kiểu khi tạo đối tượng**; việc **bỏ hẳn tham số kiểu** tạo raw type ở vị trí generic tương ứng. Hãy giữ kiểu cụ thể ở API/biến, dùng diamond trong `new`, xử lý dữ liệu không biết kiểu bằng wildcard và kiểm tra có chủ đích, để lỗi kiểu được phát hiện sớm.