# Varargs an toàn trong Java: Phân biệt bảo đảm an toàn với che cảnh báo

## 1. Trọng tâm: compiler im lặng không có nghĩa chương trình đã an toàn

Khi khai báo phương thức nhận một số lượng đối số thay đổi (*varargs*), Java sử dụng cú pháp `...`:

```java
static void printNames(String... names) {
    for (String name : names) {
        System.out.println(name);
    }
}
```

Trong phương thức, `names` có kiểu `String[]`. Đối với kiểu phần tử thông thường như `String`, mảng có thể kiểm tra được kiểu phần tử ở runtime (*reifiable type*), nên không có nguy cơ đặc thù từ việc kết hợp varargs với generic như `List<String>` hay `T`.

Tình huống cần chú ý xuất hiện khi type của phần tử varargs **không reifiable**:

```java
static void process(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

Compiler có thể cảnh báo `possible heap pollution from parameterized vararg type` ở khai báo và `unchecked generic array creation for varargs parameter` tại lời gọi, vì generic type arguments không thể được kiểm chứng đầy đủ trên mảng ở runtime.

Có hai annotation thường bị nhầm với nhau:

- **`@SafeVarargs`:** người viết phương thức/constructor **cam kết** thân mã sử dụng tham số varargs theo cách không gây thao tác không an toàn. Annotation này làm giảm những cảnh báo unchecked đặc thù cho khai báo và **các lời gọi** phương thức/constructor varargs được chú thích. Compiler **không chứng minh hộ** lời cam kết đó.
- **`@SuppressWarnings("unchecked")`:** yêu cầu compiler **không hiển thị một nhóm cảnh báo** trong phạm vi phần tử được chú thích. Nó không cam kết bản thân thao tác đã an toàn, cũng không sửa code hay thay đổi cơ chế runtime.

**Câu kết luận cần nhớ: `@SafeVarargs` chỉ nên dùng sau khi đã chứng minh việc xử lý varargs an toàn; `@SuppressWarnings` chỉ có ý nghĩa khi bạn hiểu rõ một cảnh báo cụ thể và có bằng chứng bảo đảm cho trường hợp đó. Cả hai đều không biến thao tác sai thành thao tác đúng.**

Nội dung này áp dụng trên Java hiện đại, gồm Java 17+. `@SafeVarargs` được giới thiệu từ Java 7 và hiện vẫn được hỗ trợ.

## 2. Vì sao generic varargs có thể gây `heap pollution`?

### 2.1. Varargs thực chất nhận một mảng

Khi viết:

```java
static <T> void accept(T... values) {
    System.out.println(values.length);
}
```

về mô hình lời gọi, compiler có thể tạo một mảng chứa những đối số truyền vào. Tham số `values` được xử lý như `T[]` trong thân phương thức. Với kiểu như `List<String>...`, phần tử được yêu cầu ở mức source là `List<String>`, trong khi JVM chỉ biết mảng của một kiểu runtime không mang đầy đủ type argument `String`.

```java
static void acceptLists(List<String>... values) {
    // values có kiểu source: List<String>[]
}
```

Ở runtime, mảng tương ứng không thể kiểm tra từng phần tử có thực sự là `List<String>`; type erasure loại bỏ type argument `String` khỏi kiểu runtime của `List`.

### 2.2. Non-reifiable type và reifiable type

- **Reifiable:** kiểu có thể kiểm tra đủ thông tin cần thiết ở runtime; ví dụ `String`, `String[]`, `int[]` và các kiểu raw/parameterized với wildcard không giới hạn thích hợp theo JLS.
- **Non-reifiable:** kiểu có thông tin generic bị xóa và không thể xác minh hoàn chỉnh ở runtime; ví dụ `List<String>`, `List<Integer>` và kiểu biến `T` của generic method.

Java không cho tạo trực tiếp `new List<String>[3]`. Tuy nhiên lời gọi phương thức varargs với `List<String>...` có thể tạo mảng dạng runtime tương ứng và đưa nó qua API generic, vì vậy compiler đưa ra cảnh báo ở nơi nó không thể khẳng định tính an toàn.

### 2.3. Heap pollution là gì?

**Heap pollution** xảy ra khi một biến của kiểu có tham số generic lại tham chiếu tới giá trị không phù hợp với tham số kiểu ấy. Ví dụ, một vị trí được chương trình hiểu là `List<String>` thực tế bị thay bằng `List<Integer>`.

Xét đoạn **minh họa cố ý nguy hiểm**:

```java
static void unsafe(List<String>... lists) {
    Object[] alias = lists;
    alias[0] = List.of(42);

    String text = lists[0].get(0);
    System.out.println(text);
}
```

Giả sử caller gọi `unsafe(List.of("hello"))`:

1. Tham số `lists` là mảng có kiểu phần tử generic ở source; nó có thể được xem qua tham chiếu `Object[]` vì mảng Java có quan hệ subtype với `Object[]`.
2. Phép gán `alias[0] = List.of(42)` có thể vượt qua kiểm tra runtime của mảng: đối tượng `List<Integer>` **vẫn là một `List`** ở runtime.
3. Nhưng chương trình vẫn **tin rằng** `lists[0]` là `List<String>`.
4. `lists[0].get(0)` trả về `Integer`, compiler chèn phép ép kiểu cần thiết để gán cho `String`.
5. Khi chạy, phép ép kiểu ấy gây **`ClassCastException`**.

Vấn đề không phải `List.of(42)` tự nguy hiểm, cũng không phải mảng bất kỳ đều gây heap pollution. Vấn đề là **việc dùng một alias kiểu rộng hơn để sửa nội dung mảng varargs không reifiable**, khiến kỳ vọng generic ở source không còn đúng.

Một cảnh báo unchecked cho lời gọi có thể giúp lập trình viên chú ý rằng phương thức chứa thao tác như vậy. **Che cảnh báo khi thân phương thức thực sự không an toàn làm mất tín hiệu cảnh báo mà không loại bỏ lỗi runtime.**

## 3. `@SafeVarargs` là lời cam kết về thân phương thức, không phải giấy chứng nhận của compiler

### 3.1. Khi nào được áp dụng?

`@SafeVarargs` có thể áp dụng cho **constructor hoặc phương thức varargs đủ điều kiện**, không phải cho một phương thức fixed-arity thông thường.

Trong Java hiện đại:

| Vị trí khai báo | Dùng `@SafeVarargs`? | Lý do |
| --- | --- | --- |
| `static` varargs method | Có | Không bị override theo cơ chế instance |
| `final` instance varargs method | Có | Không thể override |
| `private` instance varargs method | Có (Java 9+) | Không thể override |
| Generic/non-generic constructor có varargs | Có | Constructor không bị override |
| Instance varargs method có thể override, không `final`/`private` | Không | Override có thể thay thân xử lý, làm lời cam kết không còn đúng |
| Phương thức không có `...` | Không | Annotation không áp dụng cho fixed-arity |

Java 7 cho phép trên `static`, `final` varargs methods và constructors. Java 9 bổ sung khả năng áp dụng cho **`private` instance method**. Đây vẫn là những quy tắc được duy trì trong Java 17+.

**Không đánh dấu `@SafeVarargs` chỉ vì method varargs được phép chú thích.** Tính hợp lệ về mặt cú pháp là một việc; tính an toàn thật của phần thân là việc khác.

### 3.2. Mẫu thực sự an toàn: chỉ đọc và sao chép sang một cấu trúc có kiểu

```java
@SafeVarargs
static <T> List<T> copy(T... elements) {
    List<T> result = new ArrayList<>(elements.length);
    for (T element : elements) {
        result.add(element);
    }
    return result;
}
```

Đây là **phương thức đặt trong lớp có import `java.util.List` và `java.util.ArrayList`**, không phải tệp Java độc lập.

Tại sao cách viết này an toàn **đối với chính tham số varargs**?

- Chỉ **đọc** từng phần tử từ mảng `elements`.
- Không dùng `Object[]` hoặc raw type để gán một phần tử trái kiểu vào mảng.
- Không đưa mảng `elements` ra bên ngoài bằng cách trả về, lưu vào trường, truyền cho mã không được chứng minh an toàn hoặc tạo alias có thể sửa.
- Sao chép từng phần tử vào `ArrayList<T>` mới; caller không nhận tham chiếu trực tiếp đến mảng varargs.
- Không thực hiện ép kiểu unchecked hoặc tác vụ khiến caller tin vào một type argument sai.

`ArrayList<T>` vẫn là danh sách **mutable**; phương thức trên không tuyên bố dữ liệu bất biến, chỉ bảo vệ việc dùng mảng varargs khỏi thao tác không an toàn. Nếu phần tử `T` là đối tượng có thể thay đổi, việc sao chép cũng không biến chúng thành immutable.

### 3.3. Mẫu an toàn với nested generics

```java
@SafeVarargs
static <T> List<T> flatten(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();

    for (List<? extends T> group : groups) {
        result.addAll(group);
    }

    return result;
}
```

Trong ví dụ này, mảng varargs chứa tham chiếu tới các danh sách đầu vào; phương thức:

- Không thay phần tử của mảng bằng danh sách khác kiểu.
- Không đưa mảng ra ngoài hay lưu nó vào trạng thái có thể bị sửa sau đó.
- Chỉ đọc những phần tử từ các danh sách và đưa vào một danh sách kết quả mới.
- Tôn trọng bound `? extends T` khi đọc; không ghi phần tử vào các danh sách đầu vào.

Ví dụ sử dụng:

```java
List<String> combined =
        flatten(List.of("A"), List.of("B", "C"));
System.out.println(combined); // [A, B, C]
```

Chữ ký có `@SafeVarargs` giúp các lời gọi thông thường không bị báo cảnh báo unchecked **do việc tạo mảng varargs non-reifiable**. Nhưng vẫn phải xem thân method với cùng một tiêu chuẩn kỹ thuật như khi không có annotation.

### 3.4. "Chỉ đọc" là gợi ý hữu ích, không phải công thức chứng minh tổng quát

Việc một method không có dòng `values[i] = ...` chưa đủ để chứng minh an toàn. Ngay cả khi method chỉ đưa mảng `T[]` cho một API khác hoặc lưu mảng lại, **API hoặc mã chạy sau đó** có thể có đường thao tác không an toàn. Cần kiểm tra **toàn bộ đường truyền tham chiếu mảng**, bao gồm callback, field, helper và bất kỳ biến alias nào.

Ngược lại, hành vi thêm phần tử `T` hợp lệ vào một collection mới thường không phải nguyên nhân gây heap pollution của mảng varargs. Phải đánh giá **cách dữ liệu được sử dụng**, không chỉ đếm số dòng trong thân.

## 4. Chứng minh `@SafeVarargs` giả vẫn có thể làm chương trình lỗi

Phương thức dưới đây **cố ý không an toàn**, nhưng có đặt `@SafeVarargs`:

```java
@SafeVarargs // CỐ Ý SAI: annotation không làm thân method an toàn
static void falselyCertified(List<String>... lists) {
    Object[] alias = lists;
    alias[0] = List.of(42);

    String value = lists[0].get(0);
    System.out.println(value);
}
```

Lời gọi:

```java
falselyCertified(List.of("text"));
```

Vẫn có thể ném `ClassCastException` do heap pollution. Compiler có thể không đưa ra những cảnh báo unchecked vốn xuất hiện tại khai báo/call site của generic varargs, vì chính người viết đã **khẳng định** phương thức an toàn bằng annotation.

**Điểm tinh tế:** `javac -Xlint:varargs` có thể phát hiện và cảnh báo **một số** thao tác nghi ngờ trong thân method có `@SafeVarargs`. Điều này không biến cảnh báo thành một cơ chế chứng minh hoàn chỉnh: một số trường hợp heap pollution qua aliasing vẫn có thể lọt qua kiểm tra mà không có cảnh báo hữu ích. Quy tắc của Java **không đòi compiler chứng minh** rằng một phương thức có `@SafeVarargs` chắc chắn type-safe.

Bởi vậy không dùng cách thử “thêm `@SafeVarargs`, compile hết cảnh báo, vậy là xong”. Chứng minh dựa trên **luồng dữ liệu thực tế** và kiểm thử, không dựa trên việc warning counter trở về 0.

## 5. `@SuppressWarnings("unchecked")`: che một loại cảnh báo trong phạm vi cụ thể

### 5.1. Annotation này có ý nghĩa gì?

`@SuppressWarnings("unchecked")` yêu cầu compiler bỏ qua những cảnh báo unchecked **phát sinh trong phạm vi được chú thích** (ví dụ method hoặc một biến cục bộ thích hợp). Nó không tự động biến một generic cast không kiểm chứng thành cast có kiểm chứng.

```java
@SuppressWarnings("unchecked")
static <T> T[] uncheckedArray(int length) {
    return (T[]) new Object[length];
}
```

Đoạn này **cố ý không an toàn**: cast từ `Object[]` sang `T[]` chỉ vượt qua kiểm tra compile-time do **type erasure**. Khi caller cần kiểu mảng cụ thể, ví dụ `String[]`, JVM có thể gặp một mảng thực tế là `Object[]` và ném `ClassCastException`.

```java
String[] values = SafeVarargsWarningsDemo.<String>uncheckedArray(2);
// Có thể ném ClassCastException: runtime object thật là Object[], không phải String[].
```

Annotation chỉ che warning ở nơi được đặt; runtime type của mảng **không thay đổi**. Ngay cả khi compiler không báo dòng cast unchecked, caller vẫn có thể thất bại.

### 5.2. Phạm vi của hai annotation khác nhau

| Khía cạnh | `@SafeVarargs` | `@SuppressWarnings("unchecked")` |
| --- | --- | --- |
| Bản chất | Cam kết của người viết API rằng thân sử dụng varargs an toàn | Yêu cầu ẩn cảnh báo unchecked trong phạm vi phần tử chú thích |
| Mục đích chính | Giảm cảnh báo đặc thù generic varargs ở khai báo **và call sites** | Giảm cảnh báo unchecked **tại nơi annotation có hiệu lực** |
| Áp dụng cho | Varargs method/constructor đủ điều kiện | Các phần tử khai báo phù hợp với annotation này |
| Tác dụng với caller bên ngoài | Có thể triệt tiêu cảnh báo tạo mảng varargs tại call site của API | Annotation chỉ ở **method khai báo** không tự ẩn warning trong caller độc lập |
| Bảo đảm an toàn lúc chạy? | **Không**; đòi programmer thật sự đảm bảo | **Không**; chỉ thay đổi cảnh báo |
| Có sửa type erasure? | Không | Không |
| Có tạo cast/runtime check mới? | Không | Không |
| Có thể che vấn đề thật? | Có nếu gắn cho method không an toàn | Có nếu dùng rộng, nhất là chặn warning chưa phân tích |

Một điểm cần diễn đạt chính xác: nếu `@SuppressWarnings("unchecked")` được đặt **trực tiếp ở method caller**, nó **có thể** che một warning phát sinh tại lời gọi nằm trong scope ấy. Tuy nhiên, **đặt nó ở khai báo method được gọi** không phải cơ chế gửi lời cam kết đến mọi caller như `@SafeVarargs`.

Tương tự, `@SuppressWarnings("varargs")` là tên cảnh báo được các phiên bản `javac` hỗ trợ cho một số cảnh báo liên quan varargs. Nó vẫn là **cơ chế che cảnh báo**, không phải chứng nhận an toàn, và không có tác dụng thay thế việc phân tích thân method.

### 5.3. Khi nào `@SuppressWarnings` có thể chấp nhận?

Đôi khi có một unchecked cast không tránh được tại ranh giới với một API generic, nhưng chương trình **tự kiểm chứng toàn bộ điều kiện hợp lệ** bên ngoài khả năng của type checker. Khi đó:

1. Đặt annotation vào **phạm vi nhỏ nhất** có thể.
2. Giải thích bằng một comment **bất biến nào** đảm bảo thao tác đúng.
3. Có test cho trường hợp đúng và trường hợp dữ liệu sai.
4. Không dùng annotation làm cách bỏ qua warning chưa hiểu nguyên nhân.
5. Ưu tiên thiết kế lại API để không cần unchecked cast nếu khả thi.

Ví dụ với một biến nhận từ một API cũ, chỉ được suppress sau khi đã xác nhận ràng buộc kiểu của nguồn và contract của library. Không thể coi `@SuppressWarnings("unchecked")` là bằng chứng độc lập về an toàn.

## 6. Chương trình Java 17+ hoàn chỉnh: hai ví dụ an toàn và hai cách che lỗi

Chương trình sau được thiết kế để **chạy hoàn chỉnh** và làm nổi bật sự khác biệt:

- `copy` và `flatten`: có `@SafeVarargs`, thao tác trên mảng varargs được thiết kế an toàn.
- `falselyCertified`: có `@SafeVarargs` **sai**, dùng alias `Object[]` làm heap pollution rồi gây `ClassCastException`.
- `uncheckedArray`: có `@SuppressWarnings("unchecked")`, cast mảng không kiểm chứng gây `ClassCastException` tại caller.

Lưu thành tệp **`SafeVarargsWarningsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class SafeVarargsWarningsDemo {

    @SafeVarargs
    static <T> List<T> copy(T... elements) {
        List<T> result = new ArrayList<>(elements.length);

        for (T element : elements) {
            result.add(element);
        }

        return result;
    }

    @SafeVarargs
    static <T> List<T> flatten(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> group : groups) {
            result.addAll(group);
        }

        return result;
    }

    // CỐ Ý KHÔNG AN TOÀN: annotation không sửa hành vi Java.
    @SafeVarargs
    static void falselyCertified(List<String>... lists) {
        Object[] alias = lists;
        alias[0] = List.of(42);

        String value = lists[0].get(0);
        System.out.println(value);
    }

    // CỐ Ý KHÔNG AN TOÀN: chỉ che warning unchecked cast.
    @SuppressWarnings("unchecked")
    static <T> T[] uncheckedArray(int length) {
        return (T[]) new Object[length];
    }

    public static void main(String[] args) {
        String[] inputs = {"A", "B"};
        List<String> snapshot = copy(inputs);

        inputs[0] = "changed";
        System.out.println("copy=" + snapshot);

        System.out.println("flatten="
                + flatten(List.of("x"), List.of("y", "z")));

        try {
            falselyCertified(List.of("text"));
        } catch (ClassCastException e) {
            System.out.println("falseSafe=ClassCastException");
        }

        try {
            String[] strings =
                    SafeVarargsWarningsDemo.<String>uncheckedArray(2);
            System.out.println(strings.length);
        } catch (ClassCastException e) {
            System.out.println("suppressedCast=ClassCastException");
        }
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac SafeVarargsWarningsDemo.java
java SafeVarargsWarningsDemo
```

**Stdout chính xác:**

```text
copy=[A, B]
flatten=[x, y, z]
falseSafe=ClassCastException
suppressedCast=ClassCastException
```

Giải thích từng dòng:

1. `copy=[A, B]`: `copy` đã chép từng phần tử vào một `ArrayList` mới. Sau khi `inputs[0]` được đổi thành `"changed"`, danh sách sao chép vẫn có phần tử `"A"`. Đó là bằng chứng mảng đầu vào không bị lộ qua giá trị trả về trong ví dụ này.
2. `flatten=[x, y, z]`: phương thức chỉ đọc các `List<? extends T>` rồi đưa phần tử vào danh sách mới; không gán vào mảng varargs.
3. `falseSafe=ClassCastException`: annotation `@SafeVarargs` không làm code có alias `Object[]` thành an toàn. Exception được bắt để chương trình tiếp tục; nếu bỏ `catch`, lời gọi có thể dừng chương trình.
4. `suppressedCast=ClassCastException`: `@SuppressWarnings("unchecked")` ẩn cảnh báo ở cast bên trong method nhưng caller vẫn có thể không cast được `Object[]` thành `String[]`.

Cả hai ví dụ **cố ý sai** chỉ nhằm minh họa mối nguy. Không dùng các method này làm API trong ứng dụng sản xuất.

### 6.1. Vì sao hai ví dụ xấu đều biên dịch được?

Java generics có **type erasure**, còn annotation điều chỉnh cảnh báo chứ không thay đổi những phép kiểm tra được JVM áp dụng. Cụ thể:

- `falselyCertified` trả phần tử `Integer` trong nơi source code mong đợi `String`, nên phép ép kiểu khi đọc thất bại.
- `uncheckedArray` trả một mảng runtime `Object[]` trong khi caller mong đợi `String[]`, nên phép ép kiểu về đúng loại mảng thất bại.

Với `javac -Xlint:varargs -Xlint:unchecked`, **một số** compiler có thể đưa thêm cảnh báo cho code không an toàn trong thân `falselyCertified` dù annotation đã có mặt. Đó là tín hiệu tốt để điều tra, nhưng **không** phải bằng chứng compiler có thể phát hiện mọi đường dẫn heap pollution.

## 7. Cách kiểm tra cảnh báo bằng compiler

Để thấy thông tin cảnh báo phù hợp với code đang biên dịch, có thể chạy:

```bash
javac -Xlint:unchecked -Xlint:varargs SafeVarargsWarningsDemo.java
java SafeVarargsWarningsDemo
```

Lưu ý:

- Tùy phiên bản và cấu hình của `javac`, **nội dung và vị trí cảnh báo có thể khác nhau**, nhất là đối với phương thức được đặt `@SafeVarargs` nhưng thân có thao tác nguy hiểm. Bởi vậy bài không gán một đoạn stderr cố định cho `javac -Xlint`.
- `-Xlint:unchecked` giúp kiểm tra các chuyển đổi generic không được compiler xác minh.
- `-Xlint:varargs` giúp kiểm tra một số thao tác tiềm ẩn rủi ro liên quan varargs và các annotation.
- `-Werror` (khi được dự án lựa chọn) có thể làm bản build thất bại nếu còn warning. Nhưng nó **không chứng minh an toàn** khi người viết đã che một cảnh báo cần thiết.

Khi mã ví dụ cố ý chứa thao tác không an toàn, có thể nhận thêm warning do `-Xlint`. Đừng xóa annotation hay che thêm warning chỉ để đầu ra của bài minh họa “sạch”; hãy hiểu chúng đại diện cho nguy cơ nào.

### 7.1. Tự kiểm chứng an toàn trước khi thêm annotation

Đối với method `@SafeVarargs`, rà soát:

- Mọi cách ghi vào tham số `T...` hoặc `List<T>...`.
- Có gán qua `Object[]`, raw array hoặc cast unchecked không?
- Tham chiếu mảng varargs có thoát ra ngoài thông qua `return`, field, callback, lambda, thread hoặc phương thức khác không?
- Phương thức được gọi tiếp có thể sửa hoặc giữ lại array không?
- Type arguments có bị suy luận sai vì raw types hoặc unchecked casts ở nơi khác không?
- Có đường chạy nào khiến một phần tử không đúng kiểu được đưa vào mảng rồi đọc như kiểu mong đợi không?
- Có test đọc đúng kiểu sau những biến đổi được thực hiện không?

Khi không thể chứng minh, **đừng gắn `@SafeVarargs`**. Có thể sửa thiết kế: nhận `List<T>` thay vì varargs, sao chép vào container riêng, hoặc tránh tạo/chia sẻ mảng generic.

## 8. So sánh cách tiếp cận “sửa nguyên nhân” và “che triệu chứng”

### Tình huống A: đang sửa mảng varargs bằng alias kiểu rộng

```java
Object[] alias = values;
alias[0] = someOtherObject;
```

Nếu `values` là mảng của kiểu phần tử generic non-reifiable, thao tác này có thể làm hỏng hợp đồng generic.

**Sửa nguyên nhân:** không dùng alias `Object[]` để thay phần tử trái kiểu; thay đổi API hoặc thao tác lên collection có kiểm tra kiểu phù hợp.

**Che triệu chứng:** thêm `@SafeVarargs` vào method không an toàn. Điều này chỉ khiến warning tại caller ít hơn, **không loại bỏ heap pollution**.

### Tình huống B: generic cast không có cơ sở

```java
@SuppressWarnings("unchecked")
T[] array = (T[]) new Object[expectedLength];
```

Cast này **không thể tạo ra một mảng runtime có đúng class của `T`** chỉ nhờ annotation.

**Sửa nguyên nhân:** sử dụng `List<T>` nếu không cần array, hoặc nhận thông tin runtime về component type theo hợp đồng (ví dụ `IntFunction<T[]>` hay `Class<T>` và factory được kiểm soát) khi thực sự cần tạo mảng `T[]`.

Nếu dùng `Array.newInstance(componentClass, n)` trong một thiết kế generic, cần bảo đảm component class đúng với kiểu mà caller yêu cầu; compiler vẫn có thể cần một unchecked cast trong phần triển khai, nên phải giới hạn phạm vi và chứng minh invariant thay vì suppress toàn bộ class.

### Tình huống C: wrapper/forwarder cho varargs

Một method chỉ chuyển mảng varargs sang method khác không tự động an toàn:

```java
static <T> void forwarding(T... values) {
    otherMethod(values);
}
```

Đây là đoạn **minh họa** với `otherMethod` do ứng dụng định nghĩa. Nếu `otherMethod` lưu mảng hoặc thay phần tử qua raw/`Object[]` alias, lời gọi chuyển tiếp có thể góp phần làm mảng escape và gây heap pollution. Muốn khai báo `@SafeVarargs` cho `forwarding` cần kiểm tra cả **hành vi của bên nhận**.

### Tình huống D: API chỉ cần một collection

Nếu mục đích là nhận danh sách các danh sách, thay vì `List<T>...` có thể thiết kế:

```java
static <T> List<T> flattenLists(
        List<? extends List<? extends T>> groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

Đoạn này là **phương thức minh họa** với `java.util.List`, `java.util.ArrayList`. Nó tránh việc phải tạo mảng generic varargs, làm rõ số lượng và cấu trúc đầu vào. Khi người dùng API đã có collection, đây có thể là lựa chọn phù hợp. Ngược lại, `@SafeVarargs` vẫn hợp lý cho API varargs ngắn gọn **khi thân code thực sự an toàn**.

## 9. Khi nào không cần `@SafeVarargs`?

Không phải mọi varargs cần annotation này.

```java
static void printTexts(String... messages) {
    for (String value : messages) {
        System.out.println(value);
    }
}

static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total += number;
    }
    return total;
}
```

`String` và `int` là các kiểu phần tử reifiable; compiler không phải tạo mảng của kiểu như `List<String>` hoặc `T`. Trên các trường hợp này, `@SafeVarargs` thường không mang lại giá trị; compiler thậm chí có thể cảnh báo annotation thừa.

Ngoài ra, `@SafeVarargs` **không cho phép** áp dụng lên một phương thức instance overridable bình thường:

```java
class Parent {
    // @SafeVarargs // Sai nếu method có thể override.
    public <T> void collect(T... values) {
        System.out.println(values.length);
    }
}
```

Một method muốn dùng annotation phải đáp ứng quy tắc của Java về loại khai báo được phép, **và** nội dung an toàn thật. Đừng thêm `final`/`private` chỉ để hợp thức hóa annotation cho một method chứa thao tác rủi ro.

## 10. Kiểm thử và code review: điều gì mới tạo thành “bảo đảm”?

Một lời cam kết đáng tin phải gắn với **lập luận có thể kiểm tra**, ví dụ:

1. **Xác định đầu vào và type arguments.** Chữ ký generic, bounds và các ràng buộc với caller có nhất quán?
2. **Xem thân xử lý toàn bộ mảng.** Có write/alias/escape/unchecked cast không?
3. **Theo dõi các lời gọi phụ.** Nếu mảng được truyền sang helper, helper có làm biến đổi hoặc giữ tham chiếu không?
4. **Kiểm thử trường hợp nguy hiểm.** Dùng `List<String>` và `List<Integer>` để thấy các thao tác raw/`Object[]` có làm người dùng đọc sai kiểu không.
5. **Kiểm chứng mảng không bị lộ.** Nếu API tuyên bố “copy” thì mutate mảng đầu vào sau lời gọi và kiểm tra kết quả không bị thay đổi ngoài ý muốn.
6. **Bật cảnh báo compiler khi rà soát.** Dùng `-Xlint:unchecked`, `-Xlint:varargs`; đọc nguyên nhân thay vì chỉ đặt annotation để triệt warning.
7. **Giữ test hồi quy.** Sau khi thêm callback, cache hoặc tối ưu tránh copy, có thể vô tình biến method từng an toàn thành không an toàn.
8. **Chỉ suppress cục bộ khi có giải thích.** Đừng đặt `@SuppressWarnings("unchecked")` ở cả lớp/package để làm mất hàng loạt tín hiệu.

Một giới hạn cần hiểu: **test không chứng minh đầy đủ mọi đường thực thi trong chương trình tùy ý**. Bằng chứng đáng tin là kết hợp quy tắc kiểu, phân tích đường đi của dữ liệu và test có chủ đích. `@SafeVarargs` chính là cam kết của người viết dựa trên những bằng chứng đó, không phải một tính năng tự sửa code của compiler.

### 10.1. Mẫu code review trước khi duyệt `@SafeVarargs`

| Câu hỏi | Kết quả mong đợi |
| --- | --- |
| Method có đủ điều kiện `static`/`final`/`private` hoặc constructor không? | Có |
| Tham số thực sự là varargs (`...`) không? | Có |
| Có chứa loại phần tử non-reifiable khiến warning có ý nghĩa không? | Có hoặc giải thích nếu annotation không cần |
| Có thao tác `Object[]`, raw type, cast unchecked hay không? | Không hoặc có lập luận an toàn chặt chẽ |
| Mảng có bị đưa ra ngoài và có thể bị sửa sau đó không? | Không |
| Có helper được gọi với mảng và hành vi helper đã được kiểm tra không? | Có |
| Có test với loại phần tử generic khác nhau và aliasing không? | Có khi phù hợp |
| Cảnh báo đã được giải thích và xử lý nguyên nhân chưa? | Có |
| Phần annotation có mô tả đúng hành vi thực tế không? | Có |

**Code review nên từ chối `@SafeVarargs` không an toàn ngay cả khi build sạch cảnh báo.** Trường hợp cố ý đánh dấu an toàn sai có thể khiến người gọi mất đi cảnh báo vốn có thể giúp phát hiện lỗi.

## 11. Những nhầm lẫn phổ biến

1. **“`@SafeVarargs` buộc compiler chứng minh type safety.”** Sai. Nó là programmer assertion, không phải formal proof.
2. **“Không còn warning nghĩa là không thể `ClassCastException`.”** Sai. Ví dụ `falselyCertified` cho thấy điều ngược lại.
3. **“`@SuppressWarnings("unchecked")` sửa unchecked cast.”** Sai. Nó chỉ yêu cầu ẩn cảnh báo, runtime cast vẫn có thể thất bại.
4. **“`@SuppressWarnings` ở method khai báo tự che warning cho mọi caller.”** Sai. Phạm vi của annotation này cục bộ; chỉ `@SafeVarargs` có tác dụng đặc thù đến call site generic varargs.
5. **“Không ghi vào mảng trong chính method là đủ an toàn.”** Chưa chắc. Nếu mảng escape sang helper lưu/sửa mảng, nguy cơ vẫn còn.
6. **“Mọi `T...` hoặc `List<T>...` đều bắt buộc nguy hiểm.”** Không đúng. Nguy cơ có thể được kiểm soát bằng thiết kế và sử dụng mảng đúng cách.
7. **“`@SafeVarargs` là cách để sửa mọi unchecked warning.”** Sai. Nó chỉ giải quyết nhóm cảnh báo liên quan varargs non-reifiable trong phạm vi được đặc tả; cảnh báo unchecked khác phải được xem riêng.
8. **“Có `@SafeVarargs` thì `javac` không bao giờ cảnh báo bất kỳ điều gì trong thân method.”** Sai. Trình biên dịch vẫn có thể cảnh báo thao tác nghi ngờ trong thân, tùy loại warning và tùy chọn lint.
9. **“Phương thức overridable cũng được annotation miễn là code hiện tại an toàn.”** Sai. Java đặt giới hạn hợp lệ lên loại method vì subclass có thể thay đổi hành vi.
10. **“Đặt `@SuppressWarnings` toàn lớp sẽ tốt hơn chú thích đúng một dòng.”** Không nên. Scope rộng có thể che luôn warning mới không liên quan.
11. **“Phần tử varargs kiểu `List<String>` được JVM kiểm tra như `List<String>`.”** Sai. Type argument `String` không tồn tại dưới dạng runtime check đầy đủ cho mảng ấy.
12. **“Nếu compiler có warning thì chỉ còn cách tắt nó.”** Sai. Có thể đổi sang collection, copy an toàn hoặc sửa helper để loại bỏ nguyên nhân.

## 12. Câu hỏi ôn tập

**Câu 1.** `@SafeVarargs` có phải chứng nhận an toàn do compiler cấp không?  
**Đáp án:** Không. Đó là cam kết của lập trình viên về việc dùng tham số varargs; compiler không tự chứng minh cam kết.

**Câu 2.** `@SuppressWarnings("unchecked")` khác gì về tác dụng lên call site?  
**Đáp án:** Annotation này che cảnh báo trong phạm vi được gắn; đặt trên method được gọi không tự che warning tại caller. `@SafeVarargs` chuyên biệt có thể triệt cảnh báo unchecked liên quan tạo mảng varargs non-reifiable ở các lời gọi.

**Câu 3.** Tại sao `Object[] alias = lists; alias[0] = List.of(42);` có thể nguy hiểm khi `lists` được khai báo là `List<String>...`?  
**Đáp án:** Vì runtime kiểm tra phần tử mảng như một `List`, không kiểm tra đầy đủ `List<String>`; đọc phần tử sau có thể gây `ClassCastException`.

**Câu 4.** Method chỉ sao chép `T...` vào `List<T>` mới rồi trả danh sách có thể an toàn không?  
**Đáp án:** Có, nếu không làm mảng bị heap pollution, không lộ mảng cho code khác sửa, và mọi helper liên quan được kiểm chứng.

**Câu 5.** Có thể dùng `@SafeVarargs` cho instance method công khai, không `final` và có thể override không?  
**Đáp án:** Không. Trong Java hiện đại chỉ các varargs methods `static`, `final`, `private`, và constructors là những vị trí hợp lệ theo quy tắc của annotation.

**Câu 6.** Trong ví dụ `uncheckedArray`, tại sao caller vẫn nhận `ClassCastException`?  
**Đáp án:** Vì mảng thực tế vẫn là `Object[]`; compiler che warning ở cast generic nhưng JVM vẫn kiểm tra cast thành `String[]` khi caller yêu cầu.

**Câu 7.** Nếu có cảnh báo generic varargs, nên làm gì trước khi thêm `@SafeVarargs`?  
**Đáp án:** Phân tích mảng có bị ghi bậy, alias hay escape không; kiểm tra helper, thử những trường hợp rủi ro và sửa thiết kế nếu không đủ cơ sở chứng minh an toàn.

## 13. Tóm tắt và tài liệu chuẩn

| Nếu mục tiêu là... | Thì nên... |
| --- | --- |
| Có API generic varargs, thân thật sự type-safe | Dùng `@SafeVarargs` ở khai báo đủ điều kiện sau khi rà soát |
| Có generic array bị sửa qua `Object[]` hoặc raw alias | Sửa thao tác/thiết kế; **không** dùng annotation để che |
| Có unchecked cast tại một ranh giới được chứng minh hợp lệ | Hạn chế cast, comment invariant; nếu bắt buộc, suppress ở phạm vi nhỏ nhất |
| Không cần varargs, đã có collection | Cân nhắc tham số `List<T>` hoặc `Collection<T>` |
| Đang review warning | Bật `javac -Xlint:unchecked -Xlint:varargs` và xem nguyên nhân |
| Thấy build sạch warning | **Không** suy ra bằng chứng an toàn runtime nếu có suppressions |

**Chốt kiến thức:** **An toàn thật là tính chất của mã và luồng dữ liệu**, còn **ẩn cảnh báo là một hành động lên trình biên dịch**. `@SafeVarargs` mô tả một lời cam kết **phải đúng** về phương thức varargs; `@SuppressWarnings("unchecked")` đơn thuần giảm thông báo ở phạm vi chú thích. Khi cam kết sai hoặc unchecked cast sai, cả hai đều không ngăn `heap pollution` và `ClassCastException`.

Nguồn tham khảo chính thức (đều còn hiệu lực):

- [Java Language Specification 17, `9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): programmer assertion, hiệu ứng tại khai báo/call site, giới hạn khai báo.
- [Java Language Specification 17, `4.12.2 — Heap Pollution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2): bản chất không tương thích giữa biến generic và giá trị runtime.
- [Java SE 17 API — `java.lang.SafeVarargs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): cảnh báo compiler, điều kiện dùng annotation và ví dụ heap pollution.
- [Java SE 17 API — `java.lang.SuppressWarnings`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SuppressWarnings.html): phạm vi triệt cảnh báo; khuyến nghị đặt annotation ở phạm vi nhỏ nhất.