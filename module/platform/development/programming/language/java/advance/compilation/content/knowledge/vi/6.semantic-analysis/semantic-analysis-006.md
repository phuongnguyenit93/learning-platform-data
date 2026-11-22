# Raw type, unchecked conversion và ý nghĩa cảnh báo của javac

Trong Java, generics như **List<String>**, **Map<String, Integer>** hay **Box<T>** giúp trình biên dịch kiểm tra sự phù hợp của kiểu ngay khi viết mã. Tuy nhiên, Java vẫn cho phép dùng **raw type** như **List** hoặc **Box** mà không có tham số kiểu để tương thích với thư viện cũ. Chính lối đi tương thích này có thể làm mất bằng chứng về kiểu phần tử và sinh các cảnh báo **rawtypes**, **unchecked conversion**, **unchecked call** hoặc **unchecked cast**.

Điều quan trọng nhất cần hiểu: **cảnh báo unchecked cho biết có một thao tác mà compiler không chứng minh được an toàn kiểu tại thời điểm biên dịch**. Nó không khẳng định chương trình chắc chắn sai, nhưng không thể coi đó chỉ là thông báo trang trí. Mã có thể biên dịch và chạy một đoạn rồi phát sinh **ClassCastException**, hoặc làm một collection chứa phần tử trái với kiểu mà chương trình đang tin tưởng.

## 1. Generics bảo đảm điều gì khi không dùng raw type?

Xét đoạn Java 17+:

~~~java
import java.util.ArrayList;
import java.util.List;

public class TypedList {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        System.out.println(names.get(0));
    }
}
~~~

Tại đây **List<String>** biểu diễn một danh sách có phần tử được xử lý như **String**. Khi gọi **names.add("Lan")**, javac đối chiếu kiểu đối số với tham số kiểu **String**. Nếu thay bằng **names.add(42)**, compiler báo lỗi kiểu vì **Integer** không thể chuyển thành **String** trong lời gọi **add** này.

Biên dịch và chạy:

~~~bash
javac -d out TypedList.java
java -cp out TypedList
~~~

Kết quả:

~~~text
Lan
~~~

Sự bảo vệ từ generic phần lớn là **kiểm tra tĩnh**. Do **type erasure**, ở runtime JVM không duy trì mỗi đối tượng **ArrayList<String>** như một lớp khác biệt với **ArrayList<Integer>**. Compiler thường chèn cast thích hợp khi đọc từ kiểu có tham số để đáp ứng kiểu của biến nhận kết quả. Vì vậy một đường đi phá vỡ an toàn kiểu có thể để lại lỗi chỉ bộc lộ ở lần đọc sau.

## 2. Raw type là gì?

### 2.1. Định nghĩa và ví dụ

Với khai báo generic **G<T>**, viết tên lớp hoặc interface **G** mà bỏ danh sách đối số kiểu sẽ tạo **raw type**. Ví dụ:

| Khai báo | Phân loại | Ghi chú |
| --- | --- | --- |
| **List<String>** | Parameterized type | Phần tử có kiểu String |
| **List<Integer>** | Parameterized type | Phần tử có kiểu Integer |
| **List<?>** | Parameterized type có wildcard | Có thể đọc như Object; không biết chính xác kiểu phần tử |
| **List** | Raw type | Đã bỏ toàn bộ thông tin tham số generic ở vị trí sử dụng |
| **Map<String, Integer>** | Parameterized type | Có thông tin key/value |
| **Map** | Raw type | Không còn đối số kiểu K, V |
| **String** | Non-generic type | Không phải raw type vì String vốn không khai báo tham số kiểu |

Với generic class tự tạo:

~~~java
final class Box<T> {
    private T value;

    void set(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

**Box<String>** là kiểu có tham số; **Box** là raw type của cùng generic class. Raw type không tự tạo class riêng, không làm thay đổi source declaration **Box<T>**, và không phải từ đồng nghĩa của **Object**. **Box** vẫn là Box ở mức class, nhưng cách sử dụng các member phụ thuộc tham số **T** bị nhìn qua quy tắc erasure.

Theo JLS §4.8, khái niệm raw type còn có trường hợp array có phần tử là raw type và một số kiểu inner member class thuộc raw outer type. Với bài học cơ bản, trường hợp phổ biến nhất là viết **List** thay vì **List<E>**.

### 2.2. Raw type tồn tại để làm gì?

Generics được đưa vào Java 5, sau khi nhiều thư viện như Collections Framework đã có người dùng. Nếu compiler bắt buộc mọi mã trước Java 5 phải được sửa ngay thành **List<E>**, khả năng tương thích nguồn với code cũ sẽ bị ảnh hưởng nghiêm trọng.

Raw types cho phép:

- Code cũ truyền **List** tới một API generic mới trong một số trường hợp.
- API đã generic hóa vẫn có đường dùng cho caller cũ.
- Một dự án chuyển đổi dần từ API thiếu generics sang API được tham số hóa.

**Đây là cơ chế tương thích có chủ đích, không phải lựa chọn mặc định cho mã mới.** Khi biết kiểu phần tử, dùng **List<String>**, **List<Integer>**, **Map<Key, Value>** hoặc generic type phù hợp. Khi thực sự không biết kiểu phần tử và chỉ cần đọc, thường dùng **List<?>** thay vì raw **List**.

## 3. Phân biệt rawtypes warning và unchecked warning

Hai nhóm cảnh báo liên quan nhưng **không đồng nhất**.

### 3.1. Cảnh báo rawtypes: phát hiện dùng raw generic type

Ví dụ:

~~~java
List names = new ArrayList();
~~~

Nếu bật **-Xlint:rawtypes**, javac cảnh báo rằng **List** và **ArrayList** được dùng như raw types. Đây là lời nhắc về việc mã đang đánh mất thông tin generic. Chỉ việc khai báo một biến raw type đã có thể gây cảnh báo **rawtypes**, dù chưa có dữ liệu sai kiểu.

### 3.2. Unchecked call: gọi member qua raw type

Ví dụ:

~~~java
List values = new ArrayList();
values.add(42);
~~~

Trong generic interface **List<E>**, phương thức là **boolean add(E e)**. Khi gọi qua raw **List**, tham số **E** đã được erasure thành **Object**. javac không còn khả năng xác minh lời gọi tương thích với kiểu phần tử mà một tham chiếu generic khác kỳ vọng. Lệnh **values.add(42)** sinh cảnh báo **unchecked call to add(E)** khi bật **-Xlint:unchecked**.

**Không phải mọi lời gọi trên raw type đều phát sinh unchecked warning.** Theo JLS §4.8, cảnh báo unchecked của raw member invocation phụ thuộc việc erasure có làm thay đổi kiểu tham số của method/constructor hay không. Ví dụ đọc **values.size()** không tự tạo unchecked invocation chỉ vì receiver là raw **List**.

### 3.3. Unchecked conversion: từ raw type sang parameterized type

Ví dụ:

~~~java
List raw = new ArrayList();
List<String> strings = raw;
~~~

Ở phép gán thứ hai, javac chấp nhận **List → List<String>** theo quy tắc **unchecked conversion** (JLS §5.1.9), nhưng không chứng minh được các phần tử thực sự là **String**. Bởi vậy nó phát cảnh báo **unchecked conversion**.

Đây là quy tắc có chiều:

- **List<String> → List**: có thể gán theo tương thích raw, thường không gây cảnh báo **unchecked conversion** ở chính phép gán; khai báo raw vẫn có thể bị **rawtypes** nếu bật lint.
- **List → List<String>**: được phép qua unchecked conversion và có cảnh báo unchecked.
- **List<String> → List<Object>**: **không hợp lệ** chỉ vì String là subtype của Object; generic type ở đây bất biến (invariant).
- **List<String> → List<?>**: hợp lệ, giữ được kiểm tra kiểu theo giới hạn wildcard.

Theo JLS §5.1.9, chuyển từ raw **G** sang **G<?>** (và các tham số đều là unbounded wildcards) không cần unchecked conversion warning như chuyển sang **G<String>**. Vì vậy **List<?> view = raw;** là một hướng an toàn hơn khi chỉ cần quan sát danh sách chưa biết kiểu phần tử.

### 3.4. Unchecked cast: ép kiểu mà runtime không xác minh đủ

~~~java
Object unknown = new ArrayList<Integer>();
List<String> strings = (List<String>) unknown;
~~~

Cast này có thể được javac chấp nhận kèm **unchecked cast warning**, nhưng JVM chỉ kiểm tra đối tượng có thuộc raw class/interface **List** phù hợp hay không. Runtime không thể kiểm chứng đối số kiểu **String** của phần tử nhờ cast đó. Nếu đọc ra một phần tử **Integer** qua tham chiếu **List<String>**, chương trình có thể gặp **ClassCastException**.

Cần phân biệt:

- **Unchecked conversion** thường xuất hiện khi compiler tự cho phép chuyển kiểu raw sang parameterized trong ngữ cảnh gán/truyền đối số/trả về.
- **Unchecked cast** là chuyển kiểu tường minh do người lập trình viết, nhưng runtime không có đầy đủ thông tin generic để kiểm tra nội dung.
- **Unchecked method invocation** thường có ở lời gọi method trên raw receiver khi chữ ký đã bị erasure.
- **rawtypes** cảnh báo ngay việc dùng tên generic không có type arguments; tự nó không có nghĩa vừa xảy ra unchecked conversion.

Ngoài các ví dụ trên, một số trường hợp generic varargs, narrowing conversion hoặc override cũng có thể mang unchecked warning; không nên hiểu nhãn **unchecked** chỉ dành cho Collections.

## 4. Ví dụ 1: raw List làm hỏng lời hứa kiểu

Tạo tệp **RawRisk.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawRisk {
    static void addLegacy(List items) {
        items.add(42);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");

        List legacy = names;
        addLegacy(legacy);

        System.out.println(names.size());
        System.out.println(names.get(0));

        try {
            String value = names.get(1);
            System.out.println(value);
        } catch (ClassCastException exception) {
            System.out.println("ClassCastException");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac -Xlint:rawtypes,unchecked -d out RawRisk.java
java -cp out RawRisk
~~~

**Standard output chính xác** của chương trình:

~~~text
2
Lan
ClassCastException
~~~

Đã kiểm chứng ví dụ trên JDK 21: bước biên dịch thành công với **3 warnings** khi bật hai nhóm lint; lần chạy có stdout đúng như trên. Nội dung/chữ số dòng của các diagnostics có thể thay đổi theo JDK nên không coi chúng là stdout ổn định.

Diễn biến theo thứ tự:

1. **names** là **List<String>**: thêm **"Lan"** bằng lời gọi được kiểm tra tĩnh.
2. **legacy** là alias kiểu raw của **cùng một đối tượng list**. Phép gán này không tạo bản sao và không xóa phần tử có sẵn.
3. **addLegacy(legacy)** nhận raw **List**, gọi **add(42)**. Lời gọi tạo cảnh báo unchecked vì kiểm tra generic cho **E** không còn được bảo đảm.
4. Object Integer được chèn vào danh sách mà **names** vẫn đang được xem là **List<String>**.
5. **names.size()** vẫn là **2**, **names.get(0)** vẫn là **"Lan"**. Nhưng khi gán **names.get(1)** vào **String**, runtime cần cast phần tử Integer sang String và ném **ClassCastException**.

Đây là minh họa của **heap pollution**: trạng thái thực của đối tượng chứa giá trị không phù hợp với kiểu tham số mà một tham chiếu đang tuyên bố. Cảnh báo lúc biên dịch là tín hiệu cho **một đường đi có thể phá vỡ type safety**, ngay cả khi ngoại lệ xảy ra rất xa vị trí code bị cảnh báo.

**Vì sao không báo lỗi ở lệnh add ngay lúc chạy?** Ở bytecode, generic type arguments phần lớn đã bị erasure. Phương thức add của raw List nhận Object; JVM không tự biết rằng đối tượng ArrayList đang được caller khác xem là List<String>. Kiểm tra cast xuất hiện khi chương trình sử dụng kết quả với kiểu cụ thể.

## 5. Ví dụ 2: unchecked conversion trực tiếp

Tạo **UncheckedConversion.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class UncheckedConversion {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add(7);

        List<String> strings = raw;

        System.out.println(strings.size());
        try {
            String first = strings.get(0);
            System.out.println(first);
        } catch (ClassCastException exception) {
            System.out.println("ClassCastException");
        }
    }
}
~~~

Chạy:

~~~bash
javac -Xlint:rawtypes,unchecked -d out UncheckedConversion.java
java -cp out UncheckedConversion
~~~

**Standard output:**

~~~text
1
ClassCastException
~~~

Ví dụ đã chạy trên JDK 21. Với hai nhóm lint trên, javac báo **4 warnings**, trong đó có **unchecked call** cho **raw.add(7)** và **unchecked conversion** tại phép gán **List<String> strings = raw**; hai cảnh báo còn lại thuộc **rawtypes** vì viết raw **List** và **ArrayList**.

Phân tích tại nơi compiler kiểm tra:

~~~text
List raw = new ArrayList();
              |
              +-- Không có type argument: rawtypes warning khi bật lint

raw.add(7);
    |
    +-- Kiểu tham số add(E) không kiểm tra được như một List<String>:
        unchecked invocation warning

List<String> strings = raw;
                       |
                       +-- Compiler không chứng minh raw thật sự chứa String:
                           unchecked conversion warning

String first = strings.get(0);
                         |
                         +-- Runtime cast từ Object sang String:
                             ClassCastException khi phần tử là Integer
~~~

**Không có chuyện compiler đã kiểm tra mọi phần tử trước rồi mới cho phép phép gán.** Nếu có cơ chế kiểm tra toàn bộ nội dung tại phép gán, Java cần một phép kiểm tra runtime với đối số kiểu đã bị erasure, vốn không được cung cấp ở đây. Warning cho biết compiler bỏ qua được rào chắn tĩnh để hỗ trợ tương thích với mã cũ.

## 6. Quan hệ với type erasure và runtime check

Java generics dùng **type erasure**: các tham số kiểu được javac dùng trong phân tích tĩnh, sau đó nhiều dấu vết generic không hiện diện như một lớp runtime riêng. Ví dụ generic **List<String>** và **List<Integer>** cùng dựa trên kiểu runtime **List** / implementation tương ứng. Thông tin khai báo generic có thể còn trong metadata như chữ ký bytecode để compiler/reflection đọc; điều đó **không làm runtime kiểm tra từng phần tử tự động**.

Có ba ý cần tách biệt:

| Thao tác | Compiler có kiểm tra được? | Runtime có kiểm tra gì? |
| --- | --- | --- |
| **List<String> xs; xs.add("ok")** | Có, đối số là String | Kiểu phần tử generic thường không được kiểm tra lại ở add |
| **List raw = xs; raw.add(42)** | Không bảo đảm type argument; unchecked call | add nhận Object sau erasure |
| **String s = xs.get(1)** | Tin vào kiểu static List<String> | Cast sang String có thể thất bại nếu list đã bị ô nhiễm |
| **(List<String>) object** | Không chứng minh type argument | Cast kiểm tra raw List, không duyệt toàn bộ phần tử |
| **List<?> view = xs** | Hợp lệ, không giả định kiểu phần tử cụ thể | Đọc phần tử như Object |

**Không được suy ra mọi thao tác trên generic đều thiếu kiểm tra runtime.** Ví dụ array Java có kiểm tra kiểu phần tử runtime và có thể ném **ArrayStoreException**; đây là cơ chế khác với generic List. Mục tiêu bài này là đường đi raw/unchecked trong generics.

## 7. Khác biệt List, List<Object> và List<?>

Nhiều người sửa raw type thành **List<Object>** vì nghĩ hai kiểu tương đương. Chúng không tương đương:

~~~java
List<String> names = new ArrayList<>();
List<?> view = names;         // Hợp lệ: không biết cụ thể kiểu phần tử
Object item = view.get(0);    // Hợp lệ: đọc như Object

// List<Object> objects = names; // Lỗi biên dịch: invariant generic types
// view.add("X");                // Lỗi biên dịch: không biết capture của ?
// view.add(42);                 // Lỗi biên dịch
~~~

**List<?>** có nghĩa “một List với kiểu phần tử nào đó chưa biết”, vẫn giữ rào chắn tĩnh khi thêm phần tử. Chỉ có thể thêm **null** vào danh sách dạng **List<?>** theo contract tổng quát, dù chính implementation có thể không hỗ trợ thêm phần tử. **List<Object>** có nghĩa danh sách chấp nhận Object theo API generic; nó không thay cho mọi **List<T>**.

Đối với một API chỉ in hoặc đếm phần tử:

~~~java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
~~~

Viết **List<?>** thể hiện ý định chính xác hơn **List** và tránh đường gọi **add** thiếu kiểm tra.

Khi cần nhận bất kỳ subtype cụ thể nào của Number để đọc, có thể dùng **List<? extends Number>**; khi cần thêm Number vào một collection tương thích, có thể cân nhắc **List<? super Number>**. Wildcards là công cụ diễn đạt ràng buộc đúng kiểu, không phải một phép cast loại bỏ warning.

## 8. Cách xử lý dữ liệu raw từ API cũ mà vẫn an toàn

Nếu một thư viện cũ trả về **List** raw, không nên gán thẳng sang **List<String>** rồi hy vọng phần tử luôn đúng. Nếu cần bảo đảm, hãy nhận đầu vào bằng wildcard, kiểm tra từng phần tử và **sao chép sang một List<String> mới**.

Tạo **SafeBoundary.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeBoundary {
    static List<String> validateAndCopy(List<?> values) {
        List<String> result = new ArrayList<>();
        for (Object element : values) {
            if (!(element instanceof String name)) {
                throw new IllegalArgumentException("Expected String");
            }
            result.add(name);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(validateAndCopy(List.of("An", "Binh")));
        try {
            validateAndCopy(List.of("An", 42));
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -Xlint:rawtypes,unchecked -d out SafeBoundary.java
java -cp out SafeBoundary
~~~

**Standard output đã kiểm chứng trên JDK 21:**

~~~text
[An, Binh]
Expected String
~~~

Ví dụ này không có raw type hoặc unchecked conversion. Nếu đang nhận một tham chiếu raw từ legacy API, có thể gán nó vào **List<?>** rồi truyền vào **validateAndCopy**. Phần tử được kiểm tra bằng **instanceof String** trước khi thêm vào danh sách mới. **List.copyOf** tạo một danh sách không thể thay đổi qua các mutator thông thường; việc sao chép cũng tách khỏi danh sách nguồn có thể tiếp tục bị code legacy sửa.

Trong một chương trình thật, nên thiết kế cách xử lý **null**, dữ liệu sai định dạng và kích thước bộ nhớ theo contract. Ở ví dụ trên **null** bị từ chối vì không qua được **instanceof String**, nên phù hợp với ràng buộc của **List.copyOf**.

### 8.1. Nếu không thể sao chép?

Một số hệ thống cần giữ alias chung với dữ liệu legacy vì API có thay đổi trực tiếp. Khi đó hãy cô lập raw type tại lớp adapter, xác định contract của API cũ, kiểm tra dữ liệu trước khi sử dụng và tránh lan truyền kiểu đã cast đi khắp ứng dụng. Việc kiểm tra dữ liệu hiện tại **không tự đảm bảo** collection không bị một alias raw khác chèn phần tử sai kiểu về sau.

Nếu contract cho phép, tạo wrapper chỉ đọc, giới hạn khả năng mutation hoặc chuyển đổi về kiểu dữ liệu có validator rõ ràng sẽ dễ kiểm soát hơn cast raw một lần và cho rằng vấn đề đã biến mất.

### 8.2. Vì sao không đơn giản ép kiểu?

~~~java
Object unknown = new ArrayList<Integer>();
@SuppressWarnings("unchecked")
List<String> strings = (List<String>) unknown;
~~~

Đoạn này **chỉ minh họa cú pháp, không phải giải pháp an toàn**. Annotation tắt cảnh báo unchecked ở vị trí đó; không xác minh phần tử, không đổi đối tượng runtime, và không bảo vệ trước lỗi ClassCastException nếu sau này đọc phần tử Integer như String.

Nếu có thể kiểm tra từng phần tử và copy như ở **SafeBoundary**, hãy dùng đường đó thay vì cast unchecked.

## 9. Đọc và phân loại diagnostics của javac

Để xem cảnh báo rõ hơn khi biên dịch một tệp, dùng:

~~~bash
javac -Xlint:rawtypes,unchecked -d out RawRisk.java
~~~

Nếu chưa biết nguồn gốc warning trong dự án, có thể dùng:

~~~bash
javac -Xlint:all -d out RawRisk.java
~~~

Các nhóm quan trọng:

| Nhãn | Ý nghĩa thực hành | Hướng xử lý |
| --- | --- | --- |
| **[rawtypes]** | Code tham chiếu generic class/interface mà bỏ type arguments | Khai báo type argument hoặc wildcard phù hợp |
| **[unchecked] unchecked call** | Gọi method/constructor mà compiler không kiểm tra đầy đủ kiểu tham số | Bỏ raw receiver, tạo typed adapter hoặc xem lại API |
| **[unchecked] unchecked conversion** | Chuyển raw type sang generic type được tham số hóa mà không chứng minh được type arguments | Giữ wildcard, kiểm tra dữ liệu rồi copy hoặc sửa method signature |
| **[unchecked] unchecked cast** | Cast liên quan type argument không kiểm tra đủ tại runtime | Tránh cast; chứng minh contract và giới hạn phạm vi nếu bắt buộc |
| **[unchecked]** từ nguồn khác | Ví dụ generic varargs hoặc vài kiểu chuyển đổi khác | Đọc vị trí, method signature và quy tắc cụ thể |

**javac** thường chỉ in thông báo tổng quát như “uses unchecked or unsafe operations” nếu không bật lint chi tiết; điều đó không đồng nghĩa đã xử lý xong vấn đề. Dùng **-Xlint:unchecked** để xem thao tác unchecked, **-Xlint:rawtypes** để thấy việc dùng raw type, hoặc dùng cả hai.

**-Werror** yêu cầu coi warnings là lỗi khiến bước biên dịch thất bại. Nó hữu ích khi dự án muốn ngăn warning mới lọt vào CI:

~~~bash
javac -Xlint:rawtypes,unchecked -Werror -d out RawRisk.java
~~~

Với **RawRisk.java**, lệnh này thất bại do có warnings; không có nghĩa chương trình chứa cú pháp sai, mà do chính sách build chọn từ chối warnings. Trong dự án lớn, chỉ bật **-Werror** sau khi hiểu và xử lý các warnings hiện có, vì một số warning có thể đến từ code sinh ra hoặc API bên ngoài.

**Cách ưu tiên khi xử lý:** bắt đầu từ nguồn raw declaration hoặc raw API boundary, rồi lần theo chỗ add/cast/conversion. Đừng chỉ tắt warning ở dòng cuối mà bỏ qua nơi dữ liệu mất kiểm soát.

## 10. @SuppressWarnings: dùng chính xác và có lý do

Java hỗ trợ:

~~~java
@SuppressWarnings("unchecked")
~~~

và với phần dùng raw type:

~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
~~~

Các chuỗi **"rawtypes"** và **"unchecked"** cũng là khóa được javac dùng với **-Xlint**. Annotation có thể gắn vào method, constructor, type, field hoặc local variable theo nơi hợp lệ, để giới hạn phạm vi suppression.

Nếu bắt buộc tương tác với API cũ chưa thể thay đổi, hãy:

1. Đặt phần raw/unchecked trong một phương thức adapter nhỏ nhất có thể.
2. Giải thích bằng comment **vì sao contract bảo đảm kiểu** hoặc điều kiện nào đã được kiểm tra.
3. Nếu có thể, kiểm tra kiểu phần tử rồi sao chép thành cấu trúc typed.
4. Viết test cho dữ liệu đúng, dữ liệu sai kiểu và các đường mutation ngoài ý muốn.
5. Chỉ suppress đúng nhóm warning thực sự cần; tránh tắt toàn bộ cảnh báo module.

**SuppressWarnings không phải runtime cast và không biến unchecked code thành checked code.** Annotation chỉ ảnh hưởng việc compiler phát diagnostics theo phạm vi thích hợp. Cảnh báo biến mất không chứng minh logic an toàn; trách nhiệm chứng minh contract chuyển sang người viết code.

Đối với generic varargs, **@SafeVarargs** là một cam kết khác về tính an toàn của method/constructor đủ điều kiện; chỉ dùng khi thực sự đáp ứng contract, và không coi nó là giải pháp mặc định cho raw type hay unchecked conversion.

## 11. Phân biệt warning và compile-time error

Đoạn có raw type thường vẫn biên dịch:

~~~java
List raw = new ArrayList();
List<String> typed = raw; // Unchecked conversion warning
~~~

Nhưng những đoạn sau có thể tạo **compile-time error**, không chỉ warning:

~~~java
List<String> names = new ArrayList<>();
// names.add(42);                  // Error: Integer không phải String
// List<Object> objects = names;   // Error: generic List bất biến
// List<String> xs = new ArrayList<Integer>(); // Error: type arguments không phù hợp
~~~

Một cảnh báo là thông báo compiler phát hiện đường đi không chứng minh được an toàn nhưng ngôn ngữ vẫn cho phép vì tính tương thích. Lỗi biên dịch là nơi quy tắc ngôn ngữ từ chối đoạn mã. Không có quy tắc “warning là lỗi nhẹ, không cần xử lý”: mức độ nghiêm trọng khi chạy có thể lớn hơn một lỗi compile bị chặn sớm.

### 11.1. Vì sao mã không hỏng ngay?

Các tình huống thường thấy:

- List bị chèn phần tử sai nhưng chương trình chỉ gọi **size()**, nên chưa có cast sai kiểu.
- Phần tử sai nằm ở vị trí ít được truy cập; lỗi chỉ xảy ra khi request hoặc dữ liệu thực tế đi qua.
- Thư viện cũ trả về collection có kiểu phần tử đúng trong các test mẫu, nhưng không có contract chắc chắn cho mọi input.
- Một raw alias khác sửa collection sau khi một bên đã kiểm tra các phần tử.

Vì vậy cảnh báo unchecked có thể là tín hiệu về **lỗi tiềm ẩn khó tái hiện**, đặc biệt ở ranh giới dữ liệu nhận từ framework, serialization hoặc API cũ.

## 12. Quy trình rà soát một cảnh báo thực tế

Khi CI hoặc IDE hiển thị warning, có thể lần lượt trả lời:

1. **Đây là raw type declaration hay một thao tác unchecked cụ thể?** Bật nhóm **-Xlint** phù hợp và xem cả dòng được chỉ ra.
2. **Ai sở hữu generic declaration?** Nếu là source của dự án, sửa signature thành **List<T>**, **List<?>** hoặc kiểu phù hợp. Nếu là thư viện legacy, cân nhắc adapter.
3. **Có thao tác ghi vào collection chưa biết phần tử không?** Nếu chỉ đọc, dùng wildcard để tránh mất an toàn kiểu.
4. **Ai còn giữ alias đến cùng đối tượng?** Một cast thành **List<String>** không ngăn alias raw khác chèn Integer.
5. **Có thể validate và copy không?** Đây thường là cách loại bỏ cả cast và cảnh báo bằng một kiểm tra runtime có ý nghĩa thực sự.
6. **Nếu cần suppression, chứng minh invariant bằng gì?** Ghi rõ contract và giới hạn phạm vi suppression; bổ sung test lỗi nếu cần.
7. **Kết quả biên dịch thế nào khi bật -Werror?** Xử lý warnings có thật trước khi bật chính sách từ chối toàn bộ warnings trong pipeline.

Đối với public API, ưu tiên trả về tham số kiểu rõ ràng như **List<Customer>** hoặc **Collection<? extends Number>** thay vì **List**. Đối với boundary không biết kiểu, **List<?>** diễn đạt sự không chắc chắn thành một ràng buộc type-safe.

## 13. Bài tập thực hành

**Bài 1 — Phân loại cảnh báo**

Xét:

~~~java
List raw = new ArrayList();
raw.add("A");
List<String> names = raw;
~~~

Hãy dự đoán vị trí nào bị **rawtypes**, vị trí nào có **unchecked call** và vị trí nào có **unchecked conversion** khi biên dịch bằng **-Xlint:rawtypes,unchecked**. Sau đó tự chạy javac để đối chiếu với diagnostics.

**Bài 2 — Tìm lỗi runtime**

Từ **RawRisk.java**, thay **addLegacy(legacy)** bằng **legacy.add("Binh")**. Dự đoán stdout và giải thích vì sao không còn ClassCastException mặc dù lời gọi trên raw List vẫn unchecked. Điều này cho thấy **warning là rủi ro không chứng minh được**, không phải bằng chứng mỗi lần chạy đều sai.

**Bài 3 — Sửa API chỉ đọc**

Thay:

~~~java
static int length(List values) {
    return values.size();
}
~~~

bằng một signature không dùng raw type mà vẫn nhận được **List<String>**, **List<Integer>** và danh sách generic khác. Gợi ý: dùng **List<?>**. Giải thích vì sao **List<Object>** không phải lựa chọn thay thế tương đương.

**Bài 4 — Tạo adapter**

Giả sử API legacy trả về raw **List** chứa dữ liệu do bên ngoài gửi đến. Viết method nhận **List<?>**, kiểm tra từng phần tử là **String**, sao chép sang **List<String>** và ném ngoại lệ có thông điệp rõ ràng nếu không hợp lệ. Thử với **["A", "B"]** và **["A", 7]**.

**Bài 5 — Quan sát chính sách build**

Thử lần lượt:

~~~bash
javac -d out UncheckedConversion.java
javac -Xlint:unchecked -d out UncheckedConversion.java
javac -Xlint:rawtypes,unchecked -d out UncheckedConversion.java
javac -Xlint:rawtypes,unchecked -Werror -d out UncheckedConversion.java
~~~

So sánh mức chi tiết diagnostics và mã thoát quá trình biên dịch. **Không** giả định lệnh đầu tiên im lặng nghĩa là code đã type-safe.

## 14. Câu hỏi tự kiểm tra

- Raw **List** và **List<?>** khác nhau ở khả năng gọi **add** ra sao?
- Vì sao **List<String> → List<Object>** là lỗi, trong khi **List<String> → List<?>** hợp lệ?
- Câu lệnh nào là unchecked conversion và câu lệnh nào là unchecked invocation trong **UncheckedConversion.java**?
- Vì sao JVM có thể để Integer nằm trong một object mà biến **List<String>** đang trỏ tới?
- Tại sao lỗi chỉ xuất hiện khi đọc phần tử ra **String**?
- Vì sao **@SuppressWarnings("unchecked")** không phải cách sửa lỗi an toàn kiểu?
- Khi nào cần lựa chọn **validate-and-copy** thay vì ép kiểu?
- Khác biệt giữa **-Xlint:rawtypes**, **-Xlint:unchecked** và **-Werror** là gì?
- Vì sao warning unchecked tồn tại trong ngôn ngữ vốn hỗ trợ generics?

## 15. Nguồn tham khảo

- **Java Language Specification 21, §4.8 – Raw Types:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.8
- **JLS 21, §4.6 – Type Erasure:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6
- **JLS 21, §5.1.9 – Unchecked Conversion:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.9
- **JLS 21, §4.12.2 – Heap Pollution:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.2
- **Oracle Java 21, javac command / -Xlint:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Oracle Java Tutorials, Raw Types:** https://docs.oracle.com/javase/tutorial/java/generics/rawTypes.html

**Ghi nhớ:** **Raw type** bỏ tham số kiểu khi dùng generic declaration; **unchecked conversion/call/cast** là nơi compiler phải cho phép một thao tác mà không đủ thông tin chứng minh an toàn kiểu. Warning cảnh báo ranh giới mà trách nhiệm kiểm tra đã chuyển sang lập trình viên. Ưu tiên type arguments, wildcards và validation rõ ràng; chỉ giữ raw/unchecked trong những đoạn tương thích legacy thật sự cần thiết và được kiểm soát.