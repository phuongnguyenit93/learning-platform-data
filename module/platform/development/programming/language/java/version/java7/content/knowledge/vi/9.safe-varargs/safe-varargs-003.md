# Nguyên nhân gây heap pollution trong Java — đặc biệt với generic varargs

## 1. Mục tiêu và định nghĩa chính xác

**Heap pollution** là tình huống trong đó một biến có **kiểu generic được tham số hóa**, chẳng hạn `List<String>`, lại tham chiếu đến một đối tượng **không thật sự có kiểu tham số hóa đó**. Đây là thuật ngữ về **mất tính an toàn kiểu (type safety)** của chương trình Java, không có nghĩa bộ nhớ heap bị hỏng về mặt vật lý.

Ví dụ về sự khác biệt giữa *lời hứa* của kiểu và *dữ liệu thực tế*:

~~~java
List<String> names = new ArrayList<>();
// Theo khai báo, mỗi phần tử đọc từ names phải là String.
~~~

Khi mã chỉ dùng generics thông thường và không né kiểm tra kiểu, compiler sẽ chặn các lệnh sai như `names.add(42)`. Nhưng nếu một đường đi dùng **raw types, unchecked conversions/casts hoặc alias của mảng generic varargs**, dữ liệu hoặc tham chiếu không phù hợp có thể lọt qua. Đến lúc đọc theo kiểu được khai báo, chương trình mới gặp `ClassCastException`.

**Bối cảnh của bài:** thuộc nhóm *varargs an toàn* trong Java. Trọng tâm là nguyên nhân heap pollution khi tham số varargs có kiểu **non-reifiable** như `List<String>...` hoặc `T...`, nhưng cũng giải thích các nguyên nhân chung để không nhầm rằng chỉ varargs mới gây ra hiện tượng này.

**Các kết quả cần đạt:**

- Phân biệt `heap pollution`, `unchecked warning`, `ClassCastException` và `ArrayStoreException`.
- Hiểu mối quan hệ giữa **type erasure**, **mảng có kiểm tra kiểu phần tử ở runtime** và **generic varargs**.
- Biết vì sao mảng `List<String>[]` không thể được tạo trực tiếp, nhưng phương thức `List<String>...` vẫn khai báo được kèm cảnh báo.
- Dùng `@SafeVarargs` đúng bản chất: **cam kết của người viết** rằng phần thân thật sự an toàn, chứ không phải một cách sửa lỗi tùy tiện.
- Biết thiết kế API tránh rò rỉ hoặc ghi sai mảng varargs, nhận diện raw type và unchecked cast nguy hiểm.

**Tính hiện hành:** các quy tắc generics và heap pollution này vẫn áp dụng trong Java hiện đại. Ví dụ được kiểm thử với **Java 21**; không yêu cầu sử dụng JDK 7 cũ hay API đã legacy. `@SafeVarargs` xuất hiện từ Java 7 và được dùng rộng rãi trong Java được hỗ trợ hiện nay.

## 2. Generics giữ an toàn kiểu ra sao, và khi nào bị vượt qua?

Ở mã an toàn:

~~~java
List<String> texts = new ArrayList<>();
texts.add("Java");
// texts.add(42); // LỖI BIÊN DỊCH: int không phù hợp với String
String first = texts.get(0);
~~~

Đoạn mã này cần import `java.util.ArrayList` và `java.util.List` nếu đặt trong file riêng. Bộ kiểm tra kiểu biết `texts` là `List<String>`, do đó cấm thêm `Integer` vào danh sách thông qua tham chiếu ấy.

Tuy nhiên, Java sử dụng **type erasure** cho phần lớn generic type arguments: ở runtime, một đối tượng `ArrayList<String>` và một đối tượng `ArrayList<Integer>` đều thuộc lớp runtime `ArrayList`. JVM không có hai lớp runtime riêng mang tên `ArrayList<String>` và `ArrayList<Integer>`.

Compiler tận dụng những thông tin kiểu có ở source để kiểm tra, đồng thời có thể chèn ép kiểu lúc đọc giá trị generic đã bị xóa thông tin kiểu. Nếu chương trình làm mất tính chính xác của dữ liệu qua một đường *unchecked* hoặc mảng được alias, lỗi có thể chỉ xuất hiện **khi đọc**, không nhất thiết ở lệnh gây pollution.

### Ví dụ thường gặp: trộn raw type với generic

~~~java
List<String> names = new ArrayList<>();
List raw = names;           // raw type: không còn type argument String
raw.add(42);               // unchecked call; làm dữ liệu không phù hợp
String name = names.get(0); // Có thể ném ClassCastException
~~~

Đây là **đoạn minh họa không an toàn**, không phải đoạn mã khuyến nghị. `raw.add(42)` được compiler cảnh báo khi bật lint phù hợp. Đối tượng danh sách thực sự chứa `Integer` trong khi tham chiếu `names` vẫn khai báo `List<String>`; đó là một đường đi gây heap pollution, và phép đọc kiểu `String` sau đó có thể thất bại.

**Điểm quan trọng:** heap pollution có thể đã xảy ra **trước khi** ngoại lệ được ném. `ClassCastException` là một **triệu chứng** thường gặp, không phải định nghĩa của heap pollution. Nếu không bao giờ đọc dữ liệu qua một kiểu không phù hợp, hiện tượng đó vẫn có thể tồn tại mà chưa tạo ra lỗi quan sát được.

## 3. Tại sao generic varargs có nguy cơ heap pollution?

### 3.1. Varargs được thực thi thông qua mảng

Khi viết một phương thức:

~~~java
static void process(List<String>... groups) {
    // groups có dạng mảng: List<String>[] trong source.
}
~~~

đây là **đoạn khai báo phương thức minh họa**. Dấu `...` cho phép caller truyền nhiều đối số rời rạc, nhưng trong phương thức tham số `groups` hoạt động như một **mảng**.

Java có hai cơ chế kiểu khác nhau:

| Cơ chế | Điều xảy ra |
| --- | --- |
| Mảng Java, ví dụ `String[]` | Biết **component type** ở runtime, có thể từ chối phép ghi sai bằng `ArrayStoreException` |
| Generics, ví dụ `List<String>` | Kiểu tham số `String` không còn được giữ đầy đủ ở runtime do type erasure |
| Generic varargs `List<String>...` | Source nhìn thấy `List<String>[]`, nhưng component type của mảng runtime là `java.util.List`, không phải một kiểu reified `List<String>` |

Kiểu `List<String>` là **non-reifiable**: thông tin về tham số `String` không đầy đủ tại runtime. Do đó, mảng varargs có thể được xem qua một tham chiếu kiểu cha như `Object[]`; việc kiểm tra phần tử mảng chỉ nhìn thấy `List`, không thể phân biệt `List<String>` với `List<Integer>`.

### 3.2. Vì sao `new List<String>[2]` không hợp lệ?

~~~java
// CỐ Ý KHÔNG HỢP LỆ:
List<String>[] values = new List<String>[2];
~~~

Đây là **negative compile example**. Java không cho phép trực tiếp tạo mảng có component type generic **non-reifiable** như `List<String>`. Compiler báo lỗi trọng tâm:

~~~text
error: generic array creation
~~~

Giới hạn này tránh một loại ảo tưởng an toàn: mảng runtime không thể kiểm tra đầy đủ tham số `String` của từng `List` được thêm vào. Nhưng ngôn ngữ vẫn cho phép khai báo generic varargs với **cảnh báo unchecked**, vì có những phương thức varargs chỉ đọc dữ liệu và thật sự có thể thực hiện an toàn.

### 3.3. Alias qua `Object[]` và phép ghi sai không bị chặn

Xem lõi của tình huống:

~~~java
static String unsafeFirst(List<String>... groups) {
    Object[] alias = groups;  // Mảng reference có thể upcast lên Object[]
    alias[0] = List.of(42);   // Runtime component type là List: chấp nhận
    return groups[0].get(0); // Tại đây muốn String, nhưng thấy Integer
}
~~~

Đây là **phương thức minh họa có hành vi không an toàn**, cần đặt trong lớp có import `java.util.List`. Phép gán `alias[0] = List.of(42)` **không** ném `ArrayStoreException`, vì đối tượng `List<Integer>` vẫn là một `java.util.List` ở runtime. Nhưng `groups[0]` (theo khai báo) có kiểu `List<String>` và lại tham chiếu đến `List<Integer>`. Khi trả giá trị đầu tiên như `String`, compiler chèn kiểm tra/ép kiểu dẫn tới **`ClassCastException`**.

Đây là ví dụ điển hình của heap pollution do **aliasing một mảng có phần tử non-reifiable thông qua mảng kiểu cha non-generic**.

**Không nhầm với việc sửa danh sách ban đầu:** phép gán ở trên **thay tham chiếu tại ô thứ 0 của mảng varargs**; nó không tự sửa nội dung danh sách `List.of("hello")` mà caller đã truyền vào. Vấn đề là ô mảng đã không còn chứa đúng loại `List<String>` như chữ ký phương thức cam kết.

## 4. Ví dụ Java 21 hoàn chỉnh: đường đi an toàn và không an toàn

Tạo file `src/main/java/demo/HeapPollutionExample.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

public final class HeapPollutionExample {
    private HeapPollutionExample() {}

    @SafeVarargs
    static <T> List<T> merge(List<T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<T> group : groups) {
            result.addAll(group);
        }
        return List.copyOf(result);
    }

    static String unsafeFirst(List<String>... groups) {
        System.out.println("component=" +
                groups.getClass().getComponentType().getTypeName());
        Object[] alias = groups;
        alias[0] = List.of(42);
        return groups[0].get(0);
    }

    public static void main(String[] args) {
        System.out.println("safe=" + merge(List.of("Java"), List.of("21")));

        try {
            System.out.println("unsafe=" + unsafeFirst(List.of("hello")));
        } catch (ClassCastException ex) {
            System.out.println("unsafe=ClassCastException");
        }

        String[] text = {"ok"};
        Object[] arrayAlias = text;
        try {
            arrayAlias[0] = 42;
        } catch (ArrayStoreException ex) {
            System.out.println("array=ArrayStoreException");
        }
        System.out.println("text=" + text[0]);
    }
}
~~~

Trong thư mục chứa `src/`, dùng JDK có thể biên dịch mức Java 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/HeapPollutionExample.java
java -cp out demo.HeapPollutionExample
~~~

**Lưu ý quan trọng:** lệnh `javac` **biên dịch thành công nhưng có cảnh báo unchecked là điều mong đợi** vì chương trình cố ý chứa một phương thức varargs không an toàn. Đây không phải ví dụ production không có cảnh báo. Với JDK 21, hai nhóm thông báo xuất hiện trong kiểm thử:

~~~text
warning: [unchecked] Possible heap pollution from parameterized vararg type List<String>
warning: [unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Đường dẫn, số dòng và cách format của diagnostic có thể thay đổi theo compiler/JDK. Cảnh báo thứ nhất gắn với **khai báo phương thức** có kiểu phần tử non-reifiable; cảnh báo thứ hai gắn với **lời gọi** tạo mảng cho tham số varargs ấy. Vì `merge` được chứng minh an toàn và gắn `@SafeVarargs`, nó không phát ra các cảnh báo tương ứng.

**Stdout chính xác:**

~~~text
safe=[Java, 21]
component=java.util.List
unsafe=ClassCastException
array=ArrayStoreException
text=ok
~~~

### Giải thích kết quả

**`safe=[Java, 21]`:** `merge` chỉ duyệt các `List<T>` đã truyền vào, cộng dữ liệu vào một `ArrayList<T>` mới rồi trả về bản sao không thể chỉnh sửa qua `List.copyOf(...)`. Nó không ghi đè mảng varargs và không để mảng đó thoát ra ngoài. `@SafeVarargs` ở đây là một cam kết có cơ sở. `List.copyOf` có từ Java 10 và `List.of` có từ Java 9; toàn bộ chương trình kiểm thử với Java 21.

**`component=java.util.List`:** phần tử của mảng varargs ở runtime có kiểu `List`; JVM không giữ đối số generic `String` trong component type.

**`unsafe=ClassCastException`:** `alias[0] = List.of(42)` ghi được một `List<Integer>` vào mảng; đọc lại qua kiểu `List<String>` dẫn tới phép cast `Integer` sang `String` không thành công. Trong code này, phép nối chuỗi `"unsafe=" + ...` không in nửa dòng trước khi exception được bắt; Java phải đánh giá `unsafeFirst(...)` để tính toán đối số của `println`.

**`array=ArrayStoreException`:** khác với mảng `List[]`, mảng `String[]` thật có component type runtime là `String`. `Object[]` có thể alias nó do array covariance, nhưng khi gán `Integer` vào, kiểm tra store ở runtime phát hiện sai ngay.

**`text=ok`:** phép ghi vào mảng `String[]` bị từ chối nên phần tử gốc không đổi.

**Góc nhìn lỗi:** chương trình minh họa hai cách phát hiện vi phạm kiểu khác nhau: `ArrayStoreException` ngay lúc ghi vào mảng reifiable; `ClassCastException` muộn hơn khi đọc dữ liệu từ tham chiếu generic đã bị pollution.

## 5. Các nguyên nhân phổ biến của heap pollution

JLS mô tả hai nhóm cơ chế dẫn đến heap pollution: thao tác thiếu bảo đảm kiểu tạo nên **unchecked warnings** và **aliasing mảng có component type non-reifiable qua tham chiếu mảng kiểu cha raw/non-generic**.

| Nguyên nhân | Mã hoặc tình huống | Vì sao không an toàn |
| --- | --- | --- |
| **Raw types** | `List raw = typedList`, rồi `raw.add(wrongValue)` | Mất kiểm tra tham số generic ở chỗ ghi |
| **Unchecked conversion** | Gán một `List` raw cho `List<String>` | Compiler không thể chứng thực tất cả phần tử là `String` |
| **Unchecked cast** | Ép một tham chiếu có thông tin generic không rõ thành `List<String>` | Cast runtime thường chỉ kiểm tra lớp `List` sau erasure |
| **Generic varargs non-reifiable** | `List<String>... values`, `T... values` | Phần tử của mảng runtime không mang đủ generic type argument |
| **Alias mảng varargs qua kiểu cha** | `Object[] a = values; a[0] = List.of(42);` | Runtime kiểm tra `List`, không phân biệt `List<Integer>` và `List<String>` |
| **Để mảng varargs thoát ra ngoài** | Trả về hoặc lưu tham chiếu mảng `List<T>[]` cho code khác | Code khác có thể ghi sai về sau, ngoài phạm vi review method |
| **Gắn annotation che cảnh báo sai chỗ** | `@SafeVarargs` lên method thực sự ghi bẩn mảng | Annotation chỉ hạn chế cảnh báo, không sửa invariant |

### 5.1. Unchecked cast không biến dữ liệu thành đúng kiểu

Ví dụ kiểm tra `List<String>` từ một đối tượng không rõ kiểu là một vấn đề thiết kế API, không thể giải quyết chỉ bằng ép kiểu tùy ý:

~~~java
Object fromExternalSource = List.of(42);
// Ép sang List<String> qua kiểu thô có thể lọt qua type erasure;
// đọc phần tử sau đó có thể ném ClassCastException.
~~~

Đây là đoạn minh họa, không phải công thức ép kiểu nên dùng. Trong code thực tế, hãy **kiểm tra từng phần tử** theo schema hoặc dùng API/parser có thông tin kiểu thích hợp, thay vì lạm dụng `(List<String>)` hoặc đặt `@SuppressWarnings("unchecked")` trên một đoạn rộng.

### 5.2. Non-reifiable không đồng nghĩa với mọi generic đều sai

Một `List<String>` thông thường **không gây heap pollution** chỉ vì `String` bị erasure. Generics vẫn bảo vệ các thao tác ở nơi compiler có đủ thông tin kiểu.

Vấn đề xảy ra khi mã mở một “lối tắt” vượt qua kiểm tra đó, ví dụ raw reference, unchecked cast/conversion hoặc alias mảng varargs rồi ghi phần tử không phù hợp. Bản thân `List<String>...` gây **nguy cơ và cảnh báo** nhưng một phương thức **chỉ đọc an toàn** không nhất thiết gây pollution khi thực thi.

Ngoài ra, `List<?>` là một trường hợp *reifiable* theo định nghĩa JLS `4.7` vì tất cả tham số kiểu là wildcard không giới hạn; kiểu này không cho phép giả định phần tử là `String`. Điều đó cho thấy “có dấu góc `<>`” không đủ để kết luận mọi type là non-reifiable.

## 6. `@SafeVarargs`: cam kết an toàn, không phải phép chữa lỗi

`@SafeVarargs` là annotation trong `java.lang`, có từ Java 7. Nó thông báo với compiler rằng **người viết đảm bảo phần thân phương thức/constructor không thực hiện thao tác nguy hiểm với tham số varargs**. Khi được áp dụng hợp lệ, annotation có thể tắt cảnh báo unchecked về kiểu tham số varargs non-reifiable tại cả **khai báo** và **điểm gọi**.

**Nó không kiểm chứng an toàn thay cho lập trình viên và không sửa dữ liệu sai kiểu tại runtime.** Trong ví dụ chạy được, ta chỉ dùng `@SafeVarargs` trên `merge`, **không** gắn lên `unsafeFirst`.

### 6.1. Khi nào có thể gắn?

Java 21 cho phép áp dụng `@SafeVarargs` trên:

- Constructor có tham số varargs.
- Phương thức `static` có varargs.
- Phương thức instance `final` có varargs.
- Phương thức instance `private` có varargs (được bổ sung từ Java 9).

Không được gắn lên phương thức có số tham số cố định (*fixed arity*) hoặc phương thức instance có thể bị override. Không dùng annotation cho một method chỉ vì nó có dấu `...`; nếu phần tử varargs là kiểu reifiable như `String`, cảnh báo đó vốn không cần bị tắt.

### 6.2. Checklist trước khi dùng `@SafeVarargs`

1. Phần thân có ghi giá trị **không đúng generic type** vào mảng varargs không? Nếu có, **không an toàn**.
2. Có cast/alias mảng varargs sang `Object[]`, raw array hoặc một kiểu mảng cha rồi gán phần tử không tương thích không? Nếu có, **không an toàn**.
3. Có trả về/lưu mảng varargs để code ngoài method có thể ghi sai không? Nếu có, cần thiết kế lại hoặc phân tích kỹ việc ownership/aliasing; **đừng tự nhận là an toàn**.
4. Method chỉ duyệt, đọc phần tử theo generic contract hoặc sao chép dữ liệu sang một collection đúng kiểu mà không rò rỉ mảng? Đây thường là **trường hợp phù hợp**.
5. Có tái sử dụng mảng varargs từ caller? Với lời gọi truyền mảng có sẵn, alias có thể khiến tác dụng phụ ảnh hưởng cả caller; phải xét cả hai dạng gọi: `f(a, b)` và `f(array)`.

**Ví dụ annotation đặt sai về ngữ nghĩa**:

~~~java
@SafeVarargs // KHÔNG ĐÚNG: annotation che cảnh báo, method vẫn không an toàn
static void dangerous(List<String>... lists) {
    Object[] alias = lists;
    alias[0] = List.of(42);
}
~~~

Đây chỉ là ví dụ phản diện, **không được dùng như cách triển khai**. Compiler không nhất thiết phát hiện và báo lỗi vì annotation sai sự thật. Heap pollution vẫn có thể xảy ra.

### 6.3. `@SuppressWarnings` không phải giải pháp thay thế trọn vẹn

`@SuppressWarnings("unchecked")` thường chỉ tác động đến cảnh báo trong phạm vi đoạn mã được chú thích; `@SafeVarargs` có tác động đến cả cảnh báo ở các **điểm gọi** của varargs method theo JLS. Dùng annotation nào cũng đòi kiểm tra thực chất code có an toàn hay không.

Không nên dùng `@SuppressWarnings({"rawtypes", "unchecked"})` trên cả lớp chỉ để bản build sạch cảnh báo. Hãy sửa raw type, thiết kế API hoặc cô lập và giải thích một phép chuyển đổi thực sự đã được xác minh nếu không thể tránh.

## 7. Cách thiết kế API ít rủi ro hơn

### 7.1. Ưu tiên typed collections khi caller đã có tập dữ liệu

Nếu caller đang có một danh sách những danh sách, có thể nhận một collection có thông tin kiểu rõ ràng, thay vì bắt caller chuyển thành mảng generic varargs:

~~~java
static List<String> flatten(List<? extends List<String>> batches) {
    List<String> result = new ArrayList<>();
    for (List<String> batch : batches) {
        result.addAll(batch);
    }
    return List.copyOf(result);
}
~~~

Đây là phương thức minh họa (cần import `List` và `ArrayList`). Caller có thể truyền `List.of(List.of("A"), List.of("B"))`; compiler kiểm tra kiểu mà không phải tạo mảng `List<String>[]`. Lựa chọn này thường phù hợp hơn nếu số lượng đầu vào động.

### 7.2. Nếu phải giữ generic varargs, giữ phạm vi sử dụng mảng thật nhỏ

Đối với API tiện dụng như `merge(List<T>... groups)` trong chương trình hoàn chỉnh, hãy:

- Đọc từng phần tử theo kiểu generic được khai báo.
- Không ép mảng sang `Object[]` rồi chèn một `List` của kiểu khác.
- Không xuất bản mảng qua field, return value, callback hoặc một API ghi nội dung không kiểm soát.
- Nếu cần lưu dữ liệu lâu dài, tạo **bản sao** trong collection/đối tượng sở hữu riêng; không giữ tham chiếu đến mảng varargs mà code khác có thể chỉnh.
- Chỉ gắn `@SafeVarargs` khi đã review những đường đi có khả năng ghi hoặc làm rò rỉ tham chiếu.

### 7.3. Dùng `-Xlint` để thấy cảnh báo, không xem chúng là lỗi trang trí

Với ví dụ cố ý không an toàn:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:unchecked -d out src/main/java/demo/HeapPollutionExample.java
~~~

JDK 21 sẽ cảnh báo vị trí khai báo `unsafeFirst` và lời gọi cần tạo mảng varargs non-reifiable. Trong dự án thực tế, bật compiler warnings trong CI giúp nhận diện những đường đi có thể vượt qua type safety. Một số method generic varargs được cài đặt an toàn vẫn phát cảnh báo tại chỗ khai báo trước khi được chứng minh và chú thích; cảnh báo là **dấu hiệu cần kiểm tra**, không phải bằng chứng chắc chắn một lỗi runtime sẽ xảy ra.

### 7.4. Không cho rằng việc dùng `var` hay diamond `<>` tự gây heap pollution

~~~java
var strings = new ArrayList<String>();
List<String> names = new ArrayList<>();
~~~

Các khai báo có generic type phù hợp và không có raw/unchecked conversion thì không tự gây heap pollution. Các tính năng suy luận kiểu (`var`, diamond) giúp viết gọn, nhưng vẫn tuân theo kiểm tra kiểu tĩnh. Lỗi chính nằm ở chỗ **vượt hoặc làm mất** ràng buộc generic, không nằm ở việc viết ít chữ.

## 8. Phân biệt các lỗi và cảnh báo

| Khái niệm | Khi nào xuất hiện? | Ý nghĩa |
| --- | --- | --- |
| `unchecked warning` | **Compile time** khi không thể chứng thực an toàn kiểu generic | Dấu hiệu nguy cơ, không tự nó chứng minh đã có heap pollution lúc chạy |
| `heap pollution` | Trạng thái **tham chiếu/dữ liệu không đúng tham số generic cam kết** | Có thể xuất hiện trước khi có ngoại lệ |
| `ClassCastException` | **Runtime**, khi dữ liệu được ép/đọc như một kiểu không phù hợp | Hậu quả thường gặp của pollution, nhưng cũng có nguyên nhân khác |
| `ArrayStoreException` | **Runtime**, tại phép ghi phần tử sai vào mảng có component type runtime reifiable | Có thể chặn sai kiểu ngay lúc ghi, khác với generic erasure |
| `generic array creation` | **Compile-time error** với `new List<String>[...]` | Java cấm khởi tạo trực tiếp mảng generic non-reifiable |
| `@SafeVarargs` | Annotation có ràng buộc compile-time về vị trí áp dụng | Lời cam kết của tác giả để suppress cảnh báo liên quan, không phải bảo đảm runtime |

**Mẹo gỡ lỗi:** Nếu có `ClassCastException` khi đọc một `List<String>`, đừng chỉ sửa nơi đọc. Hãy truy ngược tất cả nơi có thể **ghi** hoặc **truyền/ép kiểu unchecked** vào danh sách và mảng bao quanh nó. Trong generic varargs, tìm code như `Object[] alias = groups`, thao tác đổi phần tử mảng, return mảng hoặc lưu mảng vào field.

## 9. Tự luyện và đáp án

**Bài 1.** Vì sao `Object[] alias = groups; alias[0] = List.of(42);` có thể không ném `ArrayStoreException` khi `groups` là `List<String>[]` do varargs tạo?

**Đáp án:** Mảng runtime có component type là `List`, vì tham số `String` đã bị erasure. `List.of(42)` vẫn là `List` ở runtime; kiểm tra array store không biết nó mang phần tử `Integer`.

**Bài 2.** Trong ví dụ trên, tại sao chương trình lại ném `ClassCastException` ở `return groups[0].get(0);`?

**Đáp án:** Chữ ký nguồn cam kết `List<String>` nên giá trị đọc được phải được dùng như `String`. Nhưng ô mảng đã bị thay bằng `List<Integer>`, nên giá trị 42 không thể cast thành `String`.

**Bài 3.** Một method có `List<String>...` và chỉ đọc các danh sách không sửa mảng. Nó có chắc chắn gây pollution không?

**Đáp án:** Không. Non-reifiable varargs làm xuất hiện **nguy cơ/cảnh báo**, không đồng nghĩa mọi lời gọi đều bị pollution. Nếu implementation thực sự an toàn và hợp lệ về điều kiện method/constructor, `@SafeVarargs` có thể diễn đạt cam kết đó.

**Bài 4.** Có nên gắn `@SafeVarargs` lên `dangerous` để làm mất warning mà không thay đổi code?

**Đáp án:** Không. Annotation không vá type safety; code vẫn có thể gây heap pollution và lỗi runtime. Phải bỏ ghi sai hoặc thay đổi thiết kế, sau đó mới xét annotation.

**Bài 5.** Tại sao `new List<String>[2]` là lỗi biên dịch trong khi `List<String>...` có thể khai báo?

**Đáp án:** Java không cho phép tạo mảng trực tiếp với component type non-reifiable. Generic varargs là cú pháp được hỗ trợ có cơ chế tạo mảng phục vụ lời gọi, kèm cảnh báo unchecked để người viết kiểm soát rủi ro.

**Bài 6.** Khi đã có `List<List<String>> batches`, có nhất thiết chuyển nó thành `List<String>[]` mới gọi được API xử lý không?

**Đáp án:** Không. Thiết kế method nhận collection, ví dụ `flatten(List<? extends List<String>> batches)`, thường đơn giản và giữ kiểm tra kiểu tốt hơn cho tập đầu vào động.

**Bài 7.** Với `List<String> names = new ArrayList<>()`, chỉ dùng `names.add("A")` và `names.get(0)` có tự tạo heap pollution không?

**Đáp án:** Không. Suy luận kiểu generic chính xác và thao tác hợp lệ được compiler kiểm tra. Cần một hành vi vượt qua type safety (raw/unchecked/alias mảng không an toàn...) mới xuất hiện nguy cơ pollution theo cơ chế đã học.

## 10. Checklist để review code

- [ ] Tìm khai báo varargs có component type non-reifiable: `T...`, `List<String>...` hoặc generic lồng nhau.
- [ ] Kiểm tra đường đi **ghi**, **alias**, **trả về** hoặc **lưu** tham số mảng varargs.
- [ ] Xác định có raw types, unchecked conversions/casts hoặc đoạn suppress warning nào không.
- [ ] Hiểu kiểu mảng runtime và giới hạn của type erasure; không mong `ArrayStoreException` kiểm tra tham số generic.
- [ ] Không gắn `@SafeVarargs` nếu method còn có thể ghi sai generic hoặc lộ mảng cho code không kiểm soát.
- [ ] Cân nhắc API dùng typed collection nếu caller đã có dữ liệu dạng collection.
- [ ] Bật `-Xlint:unchecked`/`-Xlint:all` và xem từng cảnh báo có lý do gì.
- [ ] Tách rõ **code minh họa cố ý không an toàn** với code production, và kiểm thử các tình huống đọc gây `ClassCastException` khi cần minh họa.
- [ ] Không coi việc loại bỏ warning bằng annotation là bằng chứng chương trình đã an toàn.

**Tài liệu chính thức, còn áp dụng cho Java hiện đại:**

- [JLS SE 21 `4.12.2 — Variables of Reference Type / Heap Pollution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.2): định nghĩa và những đường đi dẫn đến heap pollution.
- [JLS SE 21 `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7): loại kiểu có thông tin runtime đầy đủ.
- [JLS SE 21 `9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.7): phạm vi dùng annotation và tác động tới cảnh báo.
- [Javadoc Java 21 — SafeVarargs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/SafeVarargs.html): cam kết của programmer và ví dụ alias mảng không an toàn.
- [Dev.java — Type Erasure](https://dev.java/learn/language/fp/generics/type-erasure/): lý do generics non-reifiable và nguy cơ của unchecked operation.

**Kết luận:** Heap pollution không xuất hiện chỉ vì mã có generics hay varargs; nó xuất hiện khi một đường đi làm **tham chiếu generic chứa giá trị không còn tuân theo tham số kiểu đã cam kết**. Đặc biệt với generic varargs, sự kết hợp giữa mảng runtime và type erasure tạo cơ hội ghi sai qua alias `Object[]`. Hãy giữ API và implementation type-safe trước, chỉ dùng `@SafeVarargs` khi thực sự chứng minh được cam kết của mình.
