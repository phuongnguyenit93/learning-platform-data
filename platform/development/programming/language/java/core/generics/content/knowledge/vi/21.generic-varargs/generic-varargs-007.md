# `@SafeVarargs` là cam kết an toàn, không sửa thân phương thức

## Mục tiêu bài học

Trong Java Generics, phương thức nhận **generic varargs** như `List<String>... groups` có thể làm xuất hiện cảnh báo từ `javac` vì tham số varargs được biểu diễn bằng **mảng**, trong khi `List<String>` không phải một kiểu có thể kiểm tra đầy đủ tại runtime (*non-reifiable type*).

`@SafeVarargs` là một annotation cho phép tác giả của một số constructor/phương thức khẳng định rằng cách triển khai của mình **không thực hiện các thao tác không an toàn với varargs**. Nó có thể giảm những cảnh báo liên quan đến khai báo và điểm gọi, nhưng **không chèn runtime check mới, không bổ sung thông tin generic bị xóa, không làm sạch dữ liệu và không sửa bất kỳ câu lệnh nào trong method body**.

Sau bài này, bạn có thể:

- Giải thích đúng ý nghĩa của `@SafeVarargs`, khác biệt giữa cam kết từ tác giả và bảo đảm được runtime kiểm chứng.
- Xác định nguồn rủi ro của `List<T>...`: generic array, type erasure, array covariance và heap pollution.
- Phân biệt cảnh báo ở **khai báo**, **điểm gọi** và **bên trong thân phương thức**.
- Thấy một phương thức được gắn `@SafeVarargs` nhưng vẫn ném `ClassCastException` do chính phần triển khai không an toàn.
- Viết phương thức generic varargs chỉ đọc dữ liệu, tạo kết quả typed mới và không để array varargs thoát ra ngoài.
- Biết chính xác những loại constructor/method được phép sử dụng annotation trong Java 17+.
- Quyết định lúc nào cần bỏ `@SafeVarargs`, đổi cấu trúc API hoặc thay varargs bằng collection.
- Kiểm thử lời cam kết an toàn với trường hợp dữ liệu sai, alias, raw type và mã tiêu thụ kết quả.

Các ví dụ hoàn chỉnh đã biên dịch và chạy được trên **Java 17**; kết quả từ `javac`, `java` và `javap` được phân biệt rõ.

## 1. Định nghĩa và tư duy đúng về `@SafeVarargs`

Ví dụ khai báo một phương thức generic có varargs:

```java
@SafeVarargs
static <T> List<T> copyAll(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return List.copyOf(result);
}
```

Đoạn trên cần import `java.util.ArrayList`, `java.util.List` và đặt trong một lớp; chương trình đầy đủ ở mục 7.

Ý nghĩa của annotation là: tác giả đã kiểm tra cách dùng tham số varargs `groups` và **đứng ra bảo đảm rằng method không thực hiện thao tác thiếu an toàn với varargs có phần tử không reifiable**. Compiler không nhất thiết chứng minh được cam kết này qua mọi đường đi; nó tin vào cam kết để giảm một số cảnh báo tại khai báo và invocation.

Annotation **không**:

- Tạo thêm kiểu runtime `List<String>`.
- Biến `List<T>[]` thành một mảng có runtime component type `List<T>` riêng.
- Tự sửa phép gán hoặc cast sai.
- Kiểm tra mọi phần tử của các `List` ở runtime.
- Tự biến một implementation đang gây **heap pollution** thành implementation an toàn.
- Chặn `ClassCastException` nếu code vẫn đọc/cast dữ liệu sai.

Nói cách khác, `@SafeVarargs` giống một lời **cam kết về phương thức**, không phải công cụ chuyển đổi dữ liệu, cũng không phải lệnh yêu cầu JVM “bật generics runtime”.

## 2. Tại sao annotation không thể sửa thân method?

Một tham số `List<String>...` là `List<String>[]` ở source, nhưng runtime array chỉ kiểm tra component `List`, không kiểm tra String. Khi một method dùng `Object[]` alias để thay slot bằng `List<Integer>`, JVM có thể chấp nhận phép ghi; caller đọc phần tử dưới String sẽ ném `ClassCastException`.

```java
// Trong một static varargs method có import List:
Object[] alias = groups;     // Cùng array.
alias[0] = List.of(99);      // Runtime component là List.
String text = groups[0].get(0); // Sai kiểu khi đọc.
```

`@SafeVarargs` **không thay đổi** phép gán, cast, bytecode của body hoặc runtime component type. Nó chỉ nêu lời cam kết của tác giả để compiler giảm một số warning varargs tại declaration và caller. Compiler vẫn có thể phát `[varargs]` trong body khi thấy array alias/escape. Vì vậy ở bài này câu hỏi quyết định là **lời cam kết có đúng với implementation thực tế không?** — kể cả khi Java cho phép annotation về mặt cú pháp.

## 3. Heap pollution là rủi ro cần đánh giá

**Heap pollution (ô nhiễm kiểu trong heap)** xảy ra khi một biến của kiểu tham số hóa trỏ tới dữ liệu/đối tượng không tương thích với tham số kiểu mà biến ấy cam kết. Ví dụ `List<String>[]` được dùng để đọc các `List<String>` nhưng một ô của array thực đang chứa `List<Integer>`.

Đừng nhầm ba điều:

1. **Cảnh báo `unchecked`**: compiler không thể bảo đảm đầy đủ tính an toàn của một thao tác. Nó không đồng nghĩa chắc chắn đã có heap pollution.
2. **Heap pollution**: lời hứa kiểu ở source đã bị vi phạm đối với object/dữ liệu thực; lỗi có thể chưa xuất hiện.
3. **`ClassCastException`**: một cast runtime cụ thể thất bại, có thể là hệ quả của heap pollution hoặc một cast sai không liên quan generic.

Một `Object[]` trỏ tới `String[]` bị ghi `Integer` sẽ ném `ArrayStoreException` ngay lúc ghi, bởi JVM biết component type thật là `String`. Nhưng một `Object[]` trỏ tới varargs array `List<String>[]` có runtime component `List` **không** biết phần tử `String` bên trong list, nên phép ghi `List<Integer>` có thể lọt qua.

Không được kết luận từ một ví dụ an toàn rằng mọi generic varargs method luôn an toàn, cũng không được kết luận từ một cảnh báo rằng mọi lời gọi chắc chắn thất bại. Cần đọc **thân phương thức và đường đi của dữ liệu**.

## 4. Ví dụ phản chứng: đã gắn `@SafeVarargs` nhưng vẫn sai

Tạo tệp **`FalsePromiseDemo.java`**:

```java
import java.util.List;

public final class FalsePromiseDemo {
    @SafeVarargs
    static List<String>[] corrupt(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(99);
        return groups;
    }

    public static void main(String[] args) {
        List<String> original = List.of("safe");
        List<String>[] result = corrupt(original);

        System.out.println("original: " + original);
        System.out.println("array component: "
                + result.getClass().getComponentType().getName());

        try {
            String bad = result[0].get(0);
            System.out.println(bad);
        } catch (ClassCastException ex) {
            System.out.println("broken promise: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all FalsePromiseDemo.java
java FalsePromiseDemo
```

**Stdout đã xác minh:**

```text
original: [safe]
array component: java.util.List
broken promise: ClassCastException
```

Hãy đặc biệt chú ý: file **biên dịch được** dù annotation đang đưa ra lời cam kết sai. Compiler vẫn có thể cảnh báo một số thao tác trong thân phương thức, nhưng Java không tự biến code nguy hiểm thành an toàn chỉ vì annotation hiện diện.

### Từng bước dẫn tới lỗi

1. `main` tạo `original` là một `List<String>` chứa `"safe"`.
2. Lời gọi `corrupt(original)` sử dụng varargs. Khi đóng gói một đối số rời thành mảng, array runtime có component type `java.util.List`.
3. `Object[] alias = groups` tạo **tham chiếu thứ hai tới cùng một mảng**. Không tạo bản sao và không sao chép nội dung từng list.
4. `alias[0] = List.of(99)` thay phần tử tại slot 0 của **mảng** thành một list mới chứa `Integer`. Runtime array store chấp nhận vì list mới vẫn là đối tượng thuộc `List`.
5. Method trả `groups`, đưa **mảng đã bị ô nhiễm** ra caller dưới hợp đồng nguồn `List<String>[]`.
6. `String bad = result[0].get(0)` yêu cầu một `String` nhưng giá trị thật là `Integer`; compiler đã phát sinh cast cần thiết, dẫn đến `ClassCastException`.

Dòng:

```text
original: [safe]
```

cũng minh họa một chi tiết debugging quan trọng: code trên **không** chèn số `99` vào chính `original`. Nó thay tham chiếu trong một **slot của mảng varargs**. `original` vẫn chứa chuỗi ban đầu, trong khi `result[0]` đã trỏ tới một list khác.

Nếu chỉ quan sát `original`, bạn có thể tưởng mọi thứ an toàn. Vì vậy khi đánh giá generic varargs, cần theo dõi riêng **mảng varargs** và **các collection tham chiếu bên trong mảng**.

## 5. Compiler có thể vẫn cảnh báo code nguy hiểm trong thân method

Trong ví dụ `FalsePromiseDemo.java`, chạy `javac -Xlint:all` đã phát ra các cảnh báo `[varargs]` trên hai biểu thức:

```java
Object[] alias = groups;
return groups;
```

Đoạn cảnh báo tiêu biểu đã xác minh:

```text
warning: [varargs] Varargs method could cause heap pollution from non-reifiable varargs parameter groups
```

Trong bản JDK 17 dùng kiểm thử, chương trình đã cho **hai** cảnh báo `[varargs]`: một tại phép gán alias, một tại việc trả array varargs. Đường xuất tệp và số dòng phụ thuộc nơi biên dịch; điều cần học là **compiler phát hiện những thao tác cụ thể có thể không an toàn**.

Điều đó đồng thời chứng minh hai nhận định:

- `@SafeVarargs` có thể giảm một số cảnh báo **unchecked ở khai báo hoặc điểm gọi**, nhưng không phải “tắt mọi chẩn đoán về varargs”.
- Khi **thân phương thức** thực hiện thao tác nguy hiểm, compiler có thể vẫn phát `[varargs]` nếu bật lint phù hợp; dù không cảnh báo, code vẫn có thể sai và cần kiểm tra bằng lý luận.

Đừng đánh giá một method là an toàn chỉ vì không thấy cảnh báo trong build mặc định. Mức cảnh báo tùy `javac` flags và phiên bản JDK; quan trọng hơn là **nội dung method có làm lộ, sửa, đánh tráo hoặc chuyển varargs array sang đường không được kiểm soát không**.

## 6. Ví dụ đối chứng: không annotation thì cảnh báo ở đâu?

Tạo tệp **`UnannotatedWarningDemo.java`**:

```java
import java.util.List;

public final class UnannotatedWarningDemo {
    static void print(List<String>... groups) {
        for (List<String> group : groups) {
            System.out.println("group: " + group);
        }
    }

    public static void main(String[] args) {
        print(List.of("ok"));
    }
}
```

Chạy:

```bash
javac -Xlint:all UnannotatedWarningDemo.java
java UnannotatedWarningDemo
```

Stdout của ứng dụng:

```text
group: [ok]
```

Ở bản Java 17 đã kiểm thử, `javac -Xlint:all` phát hai cảnh báo `[unchecked]`:

```text
Possible heap pollution from parameterized vararg type List<String>
unchecked generic array creation for varargs parameter of type List<String>[]
```

Một cảnh báo nằm tại **chữ ký method**, một cảnh báo ở **lời gọi** nơi cần tạo generic varargs array. Method `print` này chỉ đọc và duyệt các `List<String>`; cảnh báo phản ánh hạn chế chứng minh an toàn của kiểu varargs, không có nghĩa bản thân `print` đã sửa sai dữ liệu.

Nếu đã kiểm tra rằng một method phù hợp như `print` thật sự không tạo heap pollution, tác giả có thể cân nhắc `@SafeVarargs` để công bố cam kết. Ngược lại, nếu chưa chứng minh được, nên giữ cảnh báo, cải tiến body hoặc thay đổi thiết kế API.

## 7. Chương trình đúng: dùng `@SafeVarargs` với thân method an toàn

Tạo tệp **`SafeVarargsContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class SafeVarargsContractDemo {
    @SafeVarargs
    static <T> List<T> copyAll(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return List.copyOf(result);
    }

    @SafeVarargs
    static <T> List<T> copyArrayElements(T... elements) {
        List<T> result = new ArrayList<>();
        for (T element : elements) {
            result.add(element);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("strings: "
                + copyAll(List.of("An"), List.of("Binh")));

        List<Number> numbers = copyAll(
                List.of(1, 2), List.of(3.5));
        System.out.println("numbers: " + numbers);

        System.out.println("elements: "
                + copyArrayElements("A", "B"));
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all SafeVarargsContractDemo.java
java SafeVarargsContractDemo
```

**Stdout đã xác minh:**

```text
strings: [An, Binh]
numbers: [1, 2, 3.5]
elements: [A, B]
```

Ở lượt biên dịch kiểm thử với `-Xlint:all`, chương trình này **không phát cảnh báo**. Nhưng điều bảo đảm phương thức an toàn không phải chỉ là số lượng cảnh báo bằng 0: **chính cách thực thi** mới là lý do có thể gắn annotation một cách có trách nhiệm.

### Kiểm tra `copyAll`

- Đọc `groups`, không ghi vào các slot của array.
- Không ép `groups` sang `Object[]` để thay phần tử.
- Không trả chính mảng varargs, không giữ nó trong field và không chuyển nó cho code có thể lưu/sửa nó.
- Với mỗi `List<? extends T>`, chỉ đọc phần tử dưới dạng `T`; không đẩy phần tử không phù hợp vào nguồn.
- Tạo một `ArrayList<T>` mới, thêm các phần tử được compiler kiểm tra, rồi trả bản sao qua `List.copyOf`.
- `List.copyOf` tạo một list không cho phép sửa trực tiếp qua API list; nếu `T` là object mutable, **phần tử không tự trở thành immutable sâu**.

Từ góc nhìn API, wildcard `? extends T` còn diễn đạt vai trò **producer** của mỗi danh sách nguồn: các phần tử được đọc từ nguồn và đưa vào danh sách kết quả.

### Kiểm tra `copyArrayElements`

Method duyệt từng phần tử `T` có trong varargs `elements`, tạo danh sách mới và không làm ô nhiễm mảng. Với các lời gọi typed thông thường, nó không đưa một giá trị không phù hợp vào array hoặc làm lộ array cho mã khác sửa.

Phương thức không ghi đè hay thay thế các slot `elements`, và không cast/chèn những đối tượng ngoài cam kết generic. Đây là mẫu đơn giản về **copy data out, do not leak the varargs array**.

Đối với cả hai method, hợp đồng còn phải nói rõ cách xử lý `null`: `List.copyOf` từ chối phần tử `null`. Đó là một chính sách API độc lập với an toàn của generic varargs; nếu muốn hỗ trợ `null`, cần chọn cách trả kết quả khác và ghi rõ hợp đồng.

## 8. Những method/constructor nào được gắn `@SafeVarargs`?

Java cho phép `@SafeVarargs` trên **constructor** và những method **không thể override** theo các điều kiện ngôn ngữ. Cụ thể:

| Vị trí | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `static` varargs method | Có | Không có override thông thường |
| `final` instance varargs method | Có | Không thể override |
| `private` instance varargs method (Java 9+) | Có | Không thể override |
| Constructor có varargs | Có | Constructor không override |
| Public/protected instance varargs method có thể override | Không | Override có thể phá lời cam kết |
| Method không phải varargs | Không | Annotation chỉ dành cho lời khai báo có variable arity |
| `String...` reifiable | Về điều kiện hợp lệ có thể được gắn, nhưng thừa | Compiler có thể cảnh báo `Redundant SafeVarargs annotation` |

Mục tiêu của giới hạn không chỉ là syntax: nếu một method có thể được lớp con override bằng thân method gây heap pollution, lời cam kết gắn trên method của lớp cha có thể không được bảo đảm khi dispatch tới implementation khác.

### Kiểm tra với Java 17

Ví dụ dưới đây biên dịch được nhưng có một cảnh báo **redundant annotation** trên constructor `String...`:

```java
public final class AnnotationEligibility {
    @SafeVarargs
    private <T> void privateMethod(T... values) {}

    @SafeVarargs
    public final <T> void finalMethod(T... values) {}

    @SafeVarargs
    public AnnotationEligibility(String... parts) {}

    public static void main(String[] args) {
        new AnnotationEligibility().privateMethod("ok");
    }
}
```

Lệnh:

```bash
javac -Xlint:all AnnotationEligibility.java
java AnnotationEligibility
```

Chương trình không in dòng nào. Compiler Java 17 đã kiểm chứng phát cảnh báo tương ứng:

```text
warning: [varargs] Redundant SafeVarargs annotation. Varargs element type String is reifiable.
```

Như vậy, `@SafeVarargs` **không cần thiết** nếu varargs component đã reifiable như `String`; mảng `String[]` ở runtime đã có kiểm tra component type đầy đủ.

### Những khai báo không hợp lệ — chỉ để phân tích

Không sao chép các đoạn dưới như một chương trình cần chạy:

```java
class InvalidExamples {
    // ERROR: public instance method có thể override.
    // @SafeVarargs
    // public <T> void overridable(T... values) {}

    // ERROR: method không nhận varargs.
    // @SafeVarargs
    // static <T> void ordinary(java.util.List<T> values) {}
}
```

Việc `@SafeVarargs` bị giới hạn ở những lời khai báo phù hợp không chứng minh body của một method hợp lệ là an toàn. Ví dụ `FalsePromiseDemo.corrupt` là `static`, nên có thể gắn annotation **về mặt vị trí cú pháp**, nhưng body vẫn cố ý phá hợp đồng.

## 9. `@SafeVarargs` thay đổi điều gì ở compile time?

Cần phân biệt **mức độ cảnh báo** và **hành vi chương trình**:

| Khía cạnh | Không annotation | Có `@SafeVarargs` đúng chỗ |
| --- | --- | --- |
| Generic varargs declaration | Có thể phát cảnh báo unchecked | Compiler có thể bỏ cảnh báo ở khai báo |
| Invocation cần tạo generic varargs array | Có thể phát cảnh báo unchecked | Compiler có thể bỏ cảnh báo ở invocation nhờ cam kết của tác giả |
| Method body có alias/write/return nguy hiểm | Vẫn nguy hiểm | **Vẫn nguy hiểm**, `-Xlint:varargs` có thể cảnh báo |
| Erasure trong bytecode | Vẫn xóa generic type arguments | Vẫn xóa generic type arguments |
| Runtime component type của varargs array | Thường là erased component `List` | **Không đổi** |
| Một phép cast sai lúc runtime | Vẫn có thể ném exception | **Không bị annotation ngăn chặn** |

Trong chương trình `FalsePromiseDemo`, một lời gọi thiếu cảnh báo unchecked tại invocation **không** làm thao tác `alias[0] = List.of(99)` an toàn. Các cảnh báo `[varargs]` trong body giúp phát hiện vấn đề, nhưng không thay thế trách nhiệm của người thiết kế API.

Cũng không nên so sánh số warning giữa hai file để kết luận file nào an toàn hơn khi chúng có body khác nhau. Hãy kiểm tra **đường đi dữ liệu**, sau đó dùng cảnh báo như công cụ hỗ trợ.

## 10. Quan sát runtime và bytecode bằng `javap`

Sau khi biên dịch `FalsePromiseDemo.java`, chạy:

```bash
javap -s -p FalsePromiseDemo
```

Trích đoạn từ kiểm thử thực tế:

```text
static java.util.List<java.lang.String>[] corrupt(java.util.List<java.lang.String>...);
  descriptor: ([Ljava/util/List;)[Ljava/util/List;
```

Đọc descriptor:

- `[` biểu thị mảng.
- `Ljava/util/List;` biểu thị một `List` ở JVM descriptor.
- `([Ljava/util/List;)[Ljava/util/List;` tức nhận và trả một **mảng `List[]`** theo erased descriptor.

Trình dịch `javap` có thể hiển thị `List<String>...` vì generic `Signature` metadata, nhưng runtime array element check chỉ có component type `List`. Đây là nguyên nhân căn bản cho thấy annotation không thể làm `String` xuất hiện trở lại ở runtime descriptor.

Muốn thấy phương thức thực sự làm gì:

```bash
javap -c -p FalsePromiseDemo
```

Hãy tìm lệnh lấy phần tử mảng, lệnh `aastore` thực hiện phép ghi array, và lệnh `checkcast java/lang/String` tại điểm đọc/cast theo kiểu nguồn. Những số offset và index constant-pool thay đổi tùy phiên bản `javac`; kết luận đúng dựa vào **opcode và descriptor**, không dựa vào chỉ số cụ thể.

`@SafeVarargs` cũng là một annotation có thể quan sát trong class-file metadata, nhưng một dấu annotation hiện diện **không sửa instruction sequence** chứa phép ghi làm sai dữ liệu.

## 11. Dấu hiệu đỏ khi review generic varargs method

Những thao tác sau cần xem xét kỹ trước khi đặt hoặc giữ `@SafeVarargs`:

**Dấu hiệu A — Upcast varargs array thành `Object[]`.**

```java
Object[] alias = groups;
```

Bản thân một tham chiếu alias chưa nhất thiết làm hỏng dữ liệu ngay tức thì. Tuy nhiên, nó mở đường cho phép ghi các phần tử không phù hợp với type arguments bị xóa, như ví dụ `FalsePromiseDemo`.

**Dấu hiệu B — Ghi vào slot của mảng varargs.**

```java
alias[0] = List.of(99);
```

Nếu `groups` được khai báo `List<String>...`, đây là thao tác đánh tráo một `List<Integer>` vào vị trí người gọi có thể nghĩ là `List<String>`.

**Dấu hiệu C — Trả chính array varargs ra caller.**

```java
return groups;
```

Việc trả mảng có thể làm lộ array để caller hoặc mã khác sửa sau này. Nguy cơ phụ thuộc chữ ký, ownership và cách caller sử dụng; đó là lý do cần tránh các API giữ hoặc xuất varargs array không kiểm soát.

**Dấu hiệu D — Lưu array vào field dùng chung.**

```java
// Minh họa thiết kế nguy hiểm:
Object[] saved = groups;
```

Nếu phần state này tồn tại sau khi lời gọi kết thúc hoặc bị code khác truy cập, mảng có thể bị thay ngoài dự kiến. Hãy cân nhắc snapshot/collection có kiểu phù hợp và quyền sửa rõ ràng.

**Dấu hiệu E — Truyền array tới helper không rõ hợp đồng.**

```java
untrustedHelper(groups);
```

Một helper có thể lưu array, cast về `Object[]` hoặc thay phần tử. Không đủ cơ sở để tuyên bố an toàn chỉ vì method hiện tại không trực tiếp chứa `aastore`.

**Dấu hiệu F — Unchecked cast/raw operations.**

```java
// Ví dụ cần ngữ cảnh khai báo array:
@SuppressWarnings("unchecked")
List<String>[] assumed = (List<String>[]) someArray;
```

Cast unchecked không kiểm tra từng phần tử của các `List`; suppression không phải bằng chứng về kiểu thực. Cần xác nhận nguồn dữ liệu hoặc đổi thiết kế.

## 12. Khi nào dùng collection thay cho varargs?

Không phải API nào cũng cần `List<T>...`. Nếu caller đã có một collection động, phương thức nhận collection thường rõ ràng hơn:

```java
static <T> List<T> flatten(
        List<? extends List<? extends T>> groups) {
    List<T> out = new ArrayList<>();
    for (List<? extends T> group : groups) {
        out.addAll(group);
    }
    return List.copyOf(out);
}
```

Đây là đoạn method minh họa; import `java.util.List`, `java.util.ArrayList` và đặt trong lớp phù hợp. Với một caller có `List<List<String>>`, nó có thể truyền danh sách các nhóm theo hợp đồng tương thích mà không cần tạo generic varargs array tại invocation.

Một phương án khác là nhận một nhóm nguồn:

```java
static <T> List<T> snapshot(
        java.util.Collection<? extends T> source) {
    return List.copyOf(source);
}
```

Lợi ích của việc bỏ varargs khi không cần thiết:

- Không cần lời cam kết `@SafeVarargs`.
- Tránh cơ chế tạo varargs array của kiểu phần tử non-reifiable tại lời gọi.
- API thể hiện rõ một tập nguồn động thay vì danh sách đối số rời.
- Dễ diễn đạt ownership (snapshot, readonly view hay live collection) và chính sách `null`.

Nhưng chuyển sang collection **không** tự chặn raw type, unchecked cast hoặc dữ liệu sai kiểu từ nguồn ngoài. An toàn kiểu vẫn phải dựa vào hợp đồng đúng và việc xác minh dữ liệu ở ranh giới nếu nguồn không đáng tin.

## 13. Cần làm gì khi dữ liệu nguồn có thể đã sai kiểu?

Giả sử thư viện legacy trả raw `List`, hoặc một deserializer cung cấp danh sách chưa được kiểm tra. Gắn `@SafeVarargs` vào một method nhận dữ liệu đó **không xác nhận** rằng list thật sự chứa các `String`.

Một adapter mẫu:

```java
static List<String> checkedStrings(List<?> input) {
    List<String> result = new ArrayList<>();
    for (int i = 0; i < input.size(); i++) {
        Object item = input.get(i);
        if (!(item instanceof String s)) {
            throw new IllegalArgumentException(
                    "Invalid String element at index " + i);
        }
        result.add(s);
    }
    return List.copyOf(result);
}
```

Đoạn method minh họa dùng `List`, `ArrayList` từ `java.util`; có thể đặt trong một class để chạy. Nó thực hiện **kiểm tra từng phần tử**, từ chối giá trị sai và `null`, rồi trả collection typed mới mà không cần unchecked cast.

Những lưu ý bổ sung:

- Một `List<?>` cho phép duyệt phần tử dưới dạng `Object` mà không cho phép ghi tùy tiện qua tham chiếu này.
- `List<String>` trong chữ ký trả về là **cam kết sau validation**, không phải kết quả của một cast vô điều kiện.
- Nếu collection đầu vào bị sửa đồng thời, cần quy tắc synchronization/snapshot phù hợp; vòng lặp kiểm tra đơn thuần không là atomic snapshot.
- Nếu phần tử bên trong là object mutable, copy list không tự tạo deep immutability.

Dùng adapter tại ranh giới giúp lỗi kiểu dữ liệu được báo ngay nơi nhận dữ liệu, thay vì xuất hiện xa hơn khi mã generic nhận một lời hứa không đúng.

## 14. Những hiểu lầm quan trọng

### “Cứ method gắn `@SafeVarargs` là compiler đã chứng minh an toàn”

Sai. Đây là **cam kết từ tác giả**, và compiler có thể không xác minh được mọi trạng thái/đường dữ liệu. `FalsePromiseDemo` có annotation hợp lệ trên `static` method mà vẫn chủ động gây heap pollution.

### “`@SafeVarargs` loại bỏ mọi warning”

Sai. `javac -Xlint:all` vẫn có thể phát cảnh báo `[varargs]` cho alias/return array nguy hiểm trong method được annotate. Raw types, unchecked casts ở nơi khác cũng có thể tiếp tục tạo warning.

### “Không warning thì runtime không thể ném `ClassCastException`”

Sai. Không warning không đồng nghĩa JVM kiểm tra mọi type argument generic. `ClassCastException` có thể đến từ cast sai hoặc dữ liệu bị làm bẩn trên một đường mà compiler không quan sát đầy đủ.

### “Annotation biến `List<String>...` thành một mảng kiểm tra `String` ở runtime”

Sai. Runtime component type bị xóa về `List`; một `List<Integer>` cũng là một `List` ở cấp runtime array store.

### “Chỉ ghi vào từng `List` mới nguy hiểm; ghi vào mảng thì không sao”

Sai. Có thể làm hỏng tham chiếu generic bằng **thay slot của varargs array**, ngay cả khi danh sách gốc `original` không bị sửa.

### “Thấy `ClassCastException` nghĩa là method body chắc chắn gây heap pollution”

Không nhất thiết. Cast sai ở những vị trí không liên quan generics cũng có thể gây exception. Để tìm root cause, truy lại nơi dữ liệu sai được đưa vào và nơi type contract bị phá.

### “`@SafeVarargs` phù hợp cho mọi instance method”

Sai. Annotation chỉ được phép trên các lời khai báo đáp ứng quy tắc không override như `final`, `private` (Java 9+) hoặc `static`, và constructor. Một instance method có thể override không đủ điều kiện.

### “Nếu varargs type reifiable như `String...`, annotation càng an toàn hơn”

Thường **không cần annotation**. Runtime `String[]` đã giữ component type, và `javac` có thể báo annotation dư thừa.

### “Một lần test thành công đủ chứng minh `@SafeVarargs` hợp lý”

Không đủ. Test thường chỉ quan sát một vài đường dữ liệu. Cần rà soát aliasing, writes, array escape, helper calls và những tình huống có phần tử sai kiểu; một build pass không thay thế lập luận về thân method.

## 15. Quy trình review một phương thức `@SafeVarargs`

Khi gặp một method đã annotate trong codebase:

1. **Đọc chữ ký:** varargs component có non-reifiable không? Ví dụ `List<T>`, `List<String>` hay chỉ `String`?
2. **Kiểm tra điều kiện đặt annotation:** constructor, static, final hoặc private method hợp lệ theo phiên bản Java mục tiêu?
3. **Tìm mọi phép gán alias:** `Object[] a = args`, ép kiểu mảng, sao chép tham chiếu vào field, return array.
4. **Tìm mọi phép ghi vào slot mảng:** `args[i] = ...`, `a[i] = ...`; đánh giá khả năng ghi một giá trị có generic argument sai.
5. **Tìm helper nhận array:** helper có lưu/đổi mảng, trả mảng, hoặc gọi code không đáng tin không?
6. **Xem các generic casts/raw conversions:** đã có điều kiện chứng minh dữ liệu đúng kiểu không?
7. **Bật compiler lint:** `-Xlint:rawtypes`, `-Xlint:unchecked`, `-Xlint:varargs`; đọc các cảnh báo ở thân method.
8. **Thử dữ liệu xấu và đường đọc typed:** xác minh không tạo heap pollution khi có những loại phần tử khác nhau.
9. **Đánh giá API thay thế:** snapshot, `Collection<? extends T>`, các method overload thích hợp hoặc cơ chế type token khi thực sự cần.
10. **Chỉ giữ annotation nếu có lập luận an toàn:** ghi rõ invariant của method để người bảo trì sau hiểu vì sao nó hợp lý.

Điểm lưu ý: một method hiện tại an toàn có thể bị thay đổi sau này. Khi refactor body của method đang mang `@SafeVarargs`, phải **xác minh lại lời cam kết** thay vì xem annotation như phần trang trí cố định.

## 16. Câu hỏi tự luyện và đáp án

**Bài 1 — Tác dụng trực tiếp của annotation**

```java
@SafeVarargs
static void f(List<String>... values) { /* ... */ }
```

`@SafeVarargs` có tự thêm runtime check cho mọi phần tử `String` không?

**Đáp án:** không. Nó là lời bảo đảm từ tác giả về sự an toàn của varargs usage; runtime component type của array vẫn bị xóa về `List`.

**Bài 2 — Phát hiện đường sai**

Một method gắn annotation viết `Object[] x = groups; x[0] = List.of(7);` khi `groups` có kiểu `List<String>...`. Có thể xem method an toàn không?

**Đáp án:** không. Slot của mảng chứa danh sách có type argument thực không tương thích với `List<String>`; nếu caller đọc như `String` có thể gây `ClassCastException`.

**Bài 3 — Ý nghĩa warning trong body**

Tại sao `javac -Xlint:all` vẫn có thể cảnh báo `[varargs]` khi method đã gắn `@SafeVarargs`?

**Đáp án:** annotation giảm một số cảnh báo khai báo/điểm gọi nhờ cam kết, nhưng compiler vẫn có thể nhận ra thao tác alias/return array có rủi ro trong body. Nó không phải cơ chế tắt mọi cảnh báo.

**Bài 4 — Vị trí dùng annotation**

Trong Java 17, constructor, private varargs, static varargs, final instance varargs và public instance varargs có thể override — những vị trí nào hợp lệ?

**Đáp án:** bốn loại đầu hợp lệ, public instance method có thể override không hợp lệ. Điều kiện cú pháp không thay thế bằng chứng an toàn body.

**Bài 5 — So sánh hai dạng mảng**

Vì sao `Object[] x = groups; x[0] = List.of(7)` có thể thành công với `List<String>...`, còn `Object[] a = new String[1]; a[0] = 7` bị `ArrayStoreException`?

**Đáp án:** component type runtime của varargs array là `List`, nên `List.of(7)` vẫn là `List`; còn array `String[]` có component type `String` và không nhận `Integer`.

**Bài 6 — Mẫu triển khai nào phù hợp?**

Một static varargs method chỉ duyệt `List<? extends T>... groups`, tạo một `ArrayList<T>` mới và trả `List.copyOf` mà không giữ/sửa mảng. Có thể gắn `@SafeVarargs` không?

**Đáp án:** có thể, sau khi đánh giá đúng mọi đường của body. Đây là mẫu an toàn trong `SafeVarargsContractDemo`; không có thao tác đánh tráo array slot hoặc để array thoát ra ngoài.

**Bài 7 — Sửa method sai**

Method `FalsePromiseDemo.corrupt` có thể sửa tối thiểu như thế nào để tránh heap pollution?

**Đáp án định hướng:** không cast mảng varargs sang `Object[]` để thay phần tử, không ghi `List<Integer>` vào array mà caller tin là `List<String>[]`, không trả một array không được kiểm soát. Nếu cần tập hợp kết quả, duyệt nguồn và trả `List<String>` hoặc `List<List<String>>` mới theo hợp đồng; lúc đó đánh giá lại có còn cần varargs/annotation không.

**Bài 8 — Kiểm tra sau khi refactor**

Một method `@SafeVarargs` trước kia chỉ đọc varargs; sau khi tối ưu, tác giả chuyển array đó sang helper mới để cache. Có thể giữ annotation mà không review lại không?

**Đáp án:** không. Helper có thể giữ hoặc thay array khiến lời cam kết cũ không còn đúng. Cần phân tích quyền sở hữu array, tham chiếu alias và mọi đường ghi/đọc trước khi giữ annotation.

## Checklist cuối bài

Trước khi đặt `@SafeVarargs`, hãy tự xác nhận:

- [ ] Khai báo varargs hợp lệ và method/constructor đủ điều kiện được annotate.
- [ ] Đã biết type arguments nào không reifiable và runtime array component type thực tế là gì.
- [ ] Body không ghi phần tử không tương thích vào mảng varargs.
- [ ] Body không đưa mảng varargs sang đường có thể bị sửa hoặc giữ ngoài kiểm soát.
- [ ] Các cast/unchecked conversions trong body có bằng chứng hợp lệ hoặc đã được thay bằng cách typed an toàn.
- [ ] Các helper mà method gọi không làm phá cam kết.
- [ ] Đã biên dịch với lint phù hợp và điều tra mọi cảnh báo quan trọng.
- [ ] Đã kiểm thử dữ liệu không phù hợp và đường đọc typed có thể phát sinh `ClassCastException`.
- [ ] Nếu phần varargs không cần thiết, đã cân nhắc dùng collection/wildcard thay thế.
- [ ] Khi implementation thay đổi, sẽ kiểm tra lại toàn bộ lời cam kết an toàn.

## Kết luận

**`@SafeVarargs` là lời cam kết có trách nhiệm của tác giả API rằng phần xử lý generic varargs không gây mất an toàn kiểu; nó không phải công cụ tự sửa code.** Vì varargs được triển khai bằng array với component type generic bị xóa, một method ghi dữ liệu sai qua `Object[]` vẫn có thể gây heap pollution và `ClassCastException`, dù đã được annotate. Chọn một cách triển khai không ghi/không làm lộ mảng varargs, tạo kết quả typed mới khi phù hợp, bật lint và xác minh đường dữ liệu — sau đó mới sử dụng `@SafeVarargs` để biểu diễn cam kết thật sự.
