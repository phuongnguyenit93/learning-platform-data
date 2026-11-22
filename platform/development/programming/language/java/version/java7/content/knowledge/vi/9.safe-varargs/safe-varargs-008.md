# Rà soát thoát tham chiếu và ghi vào mảng varargs trong Java

## 1. Mục tiêu và vấn đề cần phát hiện

Một phương thức Java dùng tham số *variable arity* (`varargs`) cho phép người gọi truyền nhiều đối số cùng loại:

~~~java
static void printAll(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
~~~

Đằng sau cú pháp `...`, tham số `values` là **một mảng**. Khi kiểu phần tử chứa tham số generic, ví dụ `List<String>...` hoặc `List<T>...`, chương trình cần được rà soát kỹ vì **type erasure** có thể khiến mảng runtime không đủ thông tin để chặn một phép ghi sai kiểu.

Bài học này tập trung vào hai câu hỏi thực tế khi đọc hoặc review phương thức varargs:

1. **Có đường nào ghi vào mảng varargs không?** Kể cả ghi trực tiếp `args[0] = ...`, ghi qua `Object[]`, dùng các hàm thao tác mảng hoặc cho hàm khác ghi.
2. **Tham chiếu tới mảng varargs có thoát khỏi phạm vi không?** Ví dụ trả mảng trực tiếp, lưu vào field, đưa vào callback/lambda dùng sau, trả một view có backing array hoặc truyền cho API có thể giữ lại nó.

Nếu một mảng varargs bị ghi sai hoặc bị lộ cho mã không kiểm soát, một tham chiếu khai báo `List<String>[]` có thể chứa phần tử `List<Integer>`. Đó là **heap pollution**: dữ liệu thực tế vi phạm hợp đồng generic mà phần mã khác đang tin tưởng. Lỗi có thể xuất hiện muộn dưới dạng `ClassCastException` khi đọc.

**Mục tiêu sau bài:** biết tìm cả **đường ghi** và **đường thoát tham chiếu**, giải thích vì sao chúng nguy hiểm với kiểu non-reifiable, xác định tình huống chỉ gây tác dụng phụ chứ chưa gây heap pollution, sửa bằng defensive copy/collection, và chỉ dùng `@SafeVarargs` khi implementation thật sự đáp ứng cam kết an toàn.

**Phiên bản:** `varargs` và generics còn được sử dụng rộng rãi trong Java hiện đại; `@SafeVarargs` có từ Java 7 và các quy tắc này vẫn còn hiệu lực. Ví dụ chính sử dụng **Java 21** để tránh phụ thuộc JDK hoặc API đã legacy.

## 2. Mảng varargs thực sự hoạt động như thế nào?

Khi khai báo:

~~~java
static void inspect(List<String>... batches) {
    System.out.println(batches.length);
}
~~~

đây là **phương thức minh họa**, cần import `java.util.List` và đặt trong một lớp để chạy. Đối với compiler, kiểu của `batches` trong thân phương thức là `List<String>[]`.

Lời gọi dưới dạng nhiều đối số:

~~~java
inspect(List.of("A"), List.of("B"));
~~~

sử dụng *variable arity invocation*: compiler tạo mảng đối số phù hợp để truyền tới phương thức. Nhưng Java không có mảng runtime với component class riêng mang tên `List<String>`. Do **type erasure**, component type runtime của mảng tạo cho lời gọi đó là `java.util.List`. Mảng runtime có thể phân biệt `String[]` với `Integer[]`, nhưng **không** thể phân biệt `List<String>[]` với `List<Integer>[]` ở mức component class.

| Kiểu trong mã nguồn | Type information ở runtime | Hệ quả khi ghi |
| --- | --- | --- |
| `String[]` | Component type `String` | Ghi `Integer` qua `Object[]` bị `ArrayStoreException` |
| `List<String>[]` do generic varargs tạo | Component type thực tế `List` | Một `List<Integer>` vẫn qua kiểm tra array store |
| `List<?>[]` | Component type `List`; wildcard không cam kết kiểu phần tử | Không được đọc phần tử thành `String` nếu chưa kiểm tra |
| `List<T>...` | Generic `T` bị erasure | Cần rà soát việc thay ô mảng hoặc để array thoát ra ngoài |

Java không cho tạo trực tiếp `new List<String>[2]` vì `List<String>` là kiểu **non-reifiable**. Generic varargs vẫn được cho phép, nhưng có thể phát sinh cảnh báo **unchecked** tại khai báo và nơi compiler tạo mảng ở điểm gọi. Cảnh báo là dấu hiệu phải review; **không phải** bằng chứng mọi varargs method đã có lỗi.

### 2.1. Vì sao `Object[]` là đường ghi nguy hiểm?

~~~java
static String poisonArray(List<String>... batches) {
    Object[] alias = batches;
    alias[0] = List.of(404);
    return batches[0].get(0);
}
~~~

Đây là **đoạn minh họa cố ý không an toàn**. `alias` và `batches` cùng trỏ tới một mảng. Phép ghi `alias[0] = List.of(404)` có thể thành công vì phần tử mới vẫn là `List` ở runtime. Nhưng khai báo `batches[0]` lại hứa hẹn `List<String>`, nên khi đọc `get(0)` dưới dạng `String`, runtime sẽ ném `ClassCastException`.

**Vị trí gây lỗi có thể khác vị trí vi phạm.** Heap pollution xảy ra khi tham chiếu mảng bị thay bằng dữ liệu sai hợp đồng; `ClassCastException` xuất hiện khi chương trình thực sự yêu cầu giá trị thành `String`. Vì vậy, khi debug lỗi cast ở nơi đọc, cần lần theo các **write path** ở nơi khác.

### 2.2. Không phải mọi phép ghi vào mảng đều gây heap pollution

Ví dụ có method:

~~~java
static void replaceFirst(String... values) {
    values[0] = "updated";
}
~~~

Đây là phương thức minh họa. `String` là kiểu reifiable, nên phép ghi này hợp lệ về mặt kiểu. Tuy nhiên, nếu caller truyền **mảng có sẵn** qua `replaceFirst(existingArray)`, chính mảng của caller sẽ bị thay đổi.

Tương tự, ghi vào một ô của `List<String>[]` bằng một `List<String>` phù hợp **không tự động** gây heap pollution, nhưng vẫn có thể là **tác dụng phụ ngoài ý muốn** nếu array được chia sẻ. Cần phân biệt **vi phạm type safety** với **vi phạm ownership / mutation contract**. Audit phải xem cả hai, không kết luận “có ghi là chắc chắn heap pollution”.

## 3. Rà soát đường ghi: hỏi “ai có thể thay các ô của mảng?”

Một audit thực tế bắt đầu bằng cách xác định mọi tham chiếu đến **chính mảng varargs**, không chỉ các biến chứa từng danh sách.

### 3.1. Ghi trực tiếp

~~~java
// Trong phương thức nhận List<String>... batches:
batches[0] = List.of("replacement");
~~~

Đây là đoạn minh họa **giả định mảng không rỗng**. Phép gán đúng generic type của phần tử không nhất thiết gây pollution, nhưng nó vẫn **thay tham chiếu trong mảng**. Nếu caller truyền mảng trực tiếp, mutation này có thể quan sát được ở caller. Đừng nhầm thay `batches[0]` với việc thêm một phần tử vào danh sách mà `batches[0]` trỏ tới: đó là hai dạng mutation khác nhau.

### 3.2. Ghi qua alias hoặc kiểu thô (raw)

~~~java
Object[] alias = batches;
alias[0] = List.of(404); // Sai hợp đồng List<String>[]
~~~

Ghi qua `Object[]` làm trình biên dịch mất thông tin `List<String>`. Kiểm tra array store ở runtime chỉ nhìn component class `List` và không phát hiện generic mismatch.

Tương tự, cast sang raw types, unchecked array types, hoặc truyền mảng cho helper nhận `Object[]` có thể bỏ rơi bảo đảm generic. Review cả đường đi **trực tiếp** lẫn **gián tiếp**:

- `Object[] alias = batches;` và mọi lệnh ghi tiếp theo vào `alias`.
- Lệnh `batches[i] = ...` và dữ liệu được dùng để gán.
- `Arrays.fill(...)`, `System.arraycopy(...)`, reflection `Array.set(...)`, `Arrays.sort(...)` hoặc thư viện tự viết nhận mảng: chúng có thể thao tác trên các ô mảng. Không phải mọi lời gọi như vậy đều sai; cần xét hợp đồng từng phương thức và kiểu giá trị được ghi.
- Helper hoặc callback được truyền mảng: liệu helper **chỉ đọc**, **thay phần tử**, **giữ lại tham chiếu** hay **trả một alias**?
- Mọi đường cast, raw reference và `@SuppressWarnings("unchecked")` dọc theo dữ liệu.

### 3.3. Ghi vào **nội dung danh sách** khác với ghi vào **ô của mảng**

~~~java
// Giả định batches[0] là List<String> có thể thay đổi:
batches[0].add("new");      // Thay đổi LIST của caller nếu cùng tham chiếu
batches[0] = List.of("new"); // Thay đổi Ô MẢNG, không sửa list cũ
~~~

Hai lệnh là **đoạn minh họa**, và `add` có thể ném `UnsupportedOperationException` nếu list không cho sửa như `List.of(...)`. Dù compiler thấy hai lệnh hợp lệ về generic type, chúng tác động tới **hai đối tượng khác nhau** và có thể xung đột với hợp đồng “chỉ đọc” của API.

Một method muốn nhận dữ liệu rồi tạo kết quả mới nên tránh cả **sửa list đầu vào** lẫn **sửa mảng varargs đầu vào**. Nếu việc sửa được cho phép, hãy ghi rõ trong Javadoc và kiểm thử khi caller dùng mảng truyền trực tiếp.

## 4. Rà soát thoát tham chiếu: những đường đi cần tìm

*Escape* có nghĩa là **một code path khác ngoài phạm vi kiểm soát của method có thể tiếp tục dùng mảng gốc** sau hoặc ngoài khoảng thời gian dự kiến. Không phải mỗi lần truyền tham số cho helper đều là escape: cần xem helper có giữ hoặc công bố tham chiếu không. Các dạng thường gặp:

| Code pattern | Vấn đề cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `return batches;` | Trả trực tiếp mảng `List<T>[]` cho caller; caller có thể ghi vào các ô mảng | Trả collection kết quả mới hoặc bản sao với hợp đồng rõ |
| `this.saved = batches;` hoặc lưu vào static field | Mảng sống lâu hơn lời gọi; code khác có thể thay nó | Copy vào cấu trúc lưu trữ riêng, định nghĩa ownership |
| `callback.accept(batches)` | Callback có thể ghi hoặc lưu mảng, nhất là với interface nhận `Object[]` | Xét hợp đồng callback; gửi snapshot nếu không kiểm soát |
| Lambda/task captures `batches` | Mảng bị giữ trong closure và dùng sau khi phương thức trả về | Tạo immutable snapshot trước khi capture |
| `return Arrays.asList(batches);` | Trả danh sách **backed by** mảng; `set(index, ...)` thay ô mảng gốc | Tạo defensive copy nếu yêu cầu cách ly |
| `Object[] alias = batches;` rồi truyền `alias` | Alias mất generic information và có thể ghi sai | Tránh alias ghi được; truyền collection read-only thích hợp |
| `return List.copyOf(...)` từ collection riêng | Không trả trực tiếp mảng; snapshot của cấu trúc ngoài | Vẫn kiểm tra độ sâu copy và tính mutable của phần tử |

### 4.1. Trả mảng: caller có thể thay phần tử sau khi method kết thúc

~~~java
static List<String>[] leakArray(List<String>... batches) {
    return batches; // LỘ MẢNG GỐC; không nên dùng như API an toàn
}
~~~

Nếu caller lấy mảng trả về rồi alias thành `Object[]`, nó có thể đặt một `List<Integer>` vào chỗ vốn được mong đợi là `List<String>`. Đoạn trên là **phương thức minh họa không an toàn** và có thể gây cảnh báo tại khai báo/điểm gọi.

Một biến local `final` hoặc tham số đánh dấu `final` **không ngăn escape hoặc mutation nội dung mảng**. `final` chỉ ngăn gán lại biến tham chiếu; nó không tự biến object được trỏ tới thành immutable.

### 4.2. View dựa trên mảng khác với defensive copy

~~~java
List<List<String>> view = Arrays.asList(batches);
~~~

Đây là **đoạn minh họa giả định `batches` có kiểu `List<String>[]` và đã import `java.util.Arrays`, `java.util.List`**. `Arrays.asList` tạo list kích thước cố định **được hỗ trợ bởi mảng truyền vào**. Không được `add`/`remove` để đổi kích thước, nhưng `view.set(0, anotherList)` có thể làm thay phần tử của mảng gốc. Nếu trả `view` ra ngoài, tức là đã gián tiếp **đưa khả năng ghi mảng** cho caller.

Để tạo cấu trúc không phơi bày mảng, chọn copy vào collection mới:

~~~java
List<List<String>> snapshot = new ArrayList<>();
for (List<String> batch : batches) {
    snapshot.add(List.copyOf(batch));
}
return List.copyOf(snapshot);
~~~

Đây là **đoạn minh họa trong một phương thức có kiểu trả về phù hợp**, không phải file độc lập. `List.copyOf(batch)` sao chép cấu trúc danh sách con thành dạng unmodifiable; `List.copyOf(snapshot)` tạo lớp chứa bên ngoài unmodifiable. Không có tham chiếu tới **mảng varargs** được xuất bản.

**Giới hạn quan trọng:** các phép copy này **không clone sâu object phần tử**. Nếu `T` là đối tượng mutable, caller vẫn có thể thay đổi trạng thái của chính các object đó. `List.copyOf(...)` cũng không chấp nhận phần tử `null`; code sản xuất cần có hợp đồng null rõ ràng hoặc cơ chế copy phù hợp.

### 4.3. Escape thông qua callback hoặc code bất đồng bộ

~~~java
// Đoạn minh họa: gửi thẳng mảng cho code có thể giữ lại nó:
callback.accept(batches);

// Nếu callback chạy sau, tạo snapshot rõ ràng trước:
List<List<String>> snapshot = new ArrayList<>();
for (List<String> batch : batches) {
    snapshot.add(List.copyOf(batch));
}
callback.accept(List.copyOf(snapshot));
~~~

Hai lời gọi là **hai phương án minh họa**, không phải code nối tiếp được khuyên chạy. `callback` phải có kiểu phù hợp với mỗi phương án. Mục đích là phân biệt **gửi trực tiếp mảng** với **gửi collection dữ liệu đã được sao chép**. Code ngoài method có thể vẫn dùng phần tử mutable nếu copy chỉ ở cấp collection; xác định rõ mức độ bất biến thật sự cần thiết.

## 5. Ví dụ Java 21 đầy đủ: đọc an toàn, copy an toàn, escape và ghi sai

Tạo file `src/main/java/demo/VarargsReviewExample.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class VarargsReviewExample {
    private VarargsReviewExample() {}

    @SafeVarargs
    static <T> List<T> flatten(List<? extends T>... batches) {
        List<T> copy = new ArrayList<>();
        for (List<? extends T> batch : batches) {
            copy.addAll(batch);
        }
        return List.copyOf(copy);
    }

    @SafeVarargs
    static <T> List<List<? extends T>> snapshot(List<? extends T>... batches) {
        List<List<? extends T>> copy = new ArrayList<>();
        for (List<? extends T> batch : batches) {
            copy.add(List.copyOf(batch));
        }
        return List.copyOf(copy);
    }

    static List<String>[] leakArray(List<String>... batches) {
        return batches;
    }

    static String poisonArray(List<String>... batches) {
        Object[] alias = batches;
        alias[0] = List.of(404);
        return batches[0].get(0);
    }

    static void modifyCaller(String... values) {
        values[0] = "modified";
    }

    public static void main(String[] args) {
        System.out.println("flatten=" + flatten(List.of("Java"), List.of("21")));
        System.out.println("snapshot=" + snapshot(List.of("A"), List.of("B")));

        try {
            System.out.println("poison=" + poisonArray(List.of("safe")));
        } catch (ClassCastException ex) {
            System.out.println("poison=ClassCastException");
        }

        List<String>[] escaped = leakArray(List.of("before"));
        Object[] alias = escaped;
        alias[0] = List.of(99);
        try {
            String text = escaped[0].get(0);
            System.out.println("escaped=" + text);
        } catch (ClassCastException ex) {
            System.out.println("escaped=ClassCastException");
        }

        String[] original = {"original"};
        modifyCaller(original);
        System.out.println("caller=" + Arrays.toString(original));
    }
}
~~~

Từ thư mục chứa `src/`, sử dụng JDK hỗ trợ `--release 21`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/VarargsReviewExample.java
java -cp out demo.VarargsReviewExample
~~~

**Kết quả stdout chính xác:**

~~~text
flatten=[Java, 21]
snapshot=[[A], [B]]
poison=ClassCastException
escaped=ClassCastException
caller=[modified]
~~~

### Diễn giải từng dòng

**`flatten=[Java, 21]`:** `flatten` chỉ đọc đầu vào và xây `ArrayList<T>` mới. Nó không trả, lưu hay ghi ô của mảng `batches`. `@SafeVarargs` ở đây có cơ sở, không phải cách “che” hành vi nguy hiểm.

**`snapshot=[[A], [B]]`:** `snapshot` tạo cấu trúc collection mới; còn dùng `List.copyOf(batch)` để tách chính các list con khỏi sự chỉnh sửa cấu trúc bên ngoài. Phần tử bên trong là `String` nên không có vấn đề object mutable trong ví dụ này. Code không xuất bản mảng varargs.

**`poison=ClassCastException`:** `poisonArray` ghi `List<Integer>` qua alias `Object[]` vào mảng mà chữ ký hứa `List<String>[]`. Không có `ArrayStoreException` khi ghi vì runtime component type là `List`. Lỗi chỉ xuất hiện khi đọc như `String`.

**`escaped=ClassCastException`:** `leakArray` trả thẳng tham chiếu mảng. Sau khi phương thức kết thúc, caller vẫn có thể ghi vào mảng qua `Object[]`. Bài kiểm thử cố ý gây pollution và lỗi khi đọc để chứng minh **việc thoát tham chiếu có thể chuyển quyền ghi không mong muốn cho code ngoài**.

**`caller=[modified]`:** `modifyCaller` có tham số `String...` là kiểu reifiable, không liên quan heap pollution generic trong ví dụ này. Nhưng caller đã truyền **mảng `String[]` có sẵn** nên phép gán vào `values[0]` sửa trực tiếp mảng ấy. Đây là một bug khác về **mutability/ownership** mà code review varargs cũng phải phát hiện.

### Cảnh báo compiler là một phần của bài thử

Bản code cố tình chứa hai phương thức không an toàn (`leakArray`, `poisonArray`). Với `javac --release 21 -Xlint:all`, lệnh **biên dịch thành công** và dự kiến nhận bốn cảnh báo unchecked:

- Hai cảnh báo ở khai báo mỗi phương thức với dạng `Possible heap pollution from parameterized vararg type List<String>`.
- Hai cảnh báo ở nơi gọi tương ứng với dạng `unchecked generic array creation for varargs parameter of type List<String>[]`.

Đường dẫn, số dòng và cách hiển thị cảnh báo tùy máy. Hai phương thức có `@SafeVarargs` (`flatten`, `snapshot`) không phát cảnh báo trong ví dụ đã kiểm thử vì thân không công bố hoặc ghi sai mảng. **Không đưa `leakArray`/`poisonArray` vào API sản xuất**; chúng chỉ để quan sát rủi ro.

## 6. Đánh giá `@SafeVarargs`: chứng minh, không tin mù quáng

`@SafeVarargs` nói rằng người viết đã kiểm tra phần thân method/constructor **không thực hiện thao tác tiềm ẩn mất an toàn trên mảng varargs**. Nó ngăn một số *unchecked warnings* ở khai báo và **điểm gọi**, nhưng không thay đổi kiểm tra kiểu runtime và không tự chứng minh implementation đúng.

### 6.1. Khi nào annotation hợp lệ?

Trong Java 21, `@SafeVarargs` chỉ có thể đặt trên:

- Constructor nhận varargs.
- Phương thức `static` nhận varargs.
- Phương thức instance `final` nhận varargs.
- Phương thức instance `private` nhận varargs.

Không đặt trên phương thức instance có thể bị override, không đặt trên phương thức không có varargs. Với varargs component type reifiable như `String` hay `int`, annotation thường không cần thiết vì cảnh báo generic-varargs đang nói tới không phát sinh.

### 6.2. Sai lầm: gắn annotation lên method chưa an toàn

~~~java
@SafeVarargs // CỐ Ý SAI VỀ NGỮ NGHĨA: annotation không sửa heap pollution
static void mislabel(List<String>... batches) {
    Object[] alias = batches;
    alias[0] = List.of(404);
}
~~~

Đây là **đoạn phản ví dụ**, không phải code nên dùng. Ngay cả khi mã không phát warning unchecked như mong đợi, nó vẫn cho phép viết sai tham chiếu. Javadoc `SafeVarargs` có ví dụ tương tự; compiler không nhất thiết phát hiện và cấm mọi thao tác nguy hiểm được người viết che bằng annotation.

Một điểm tinh tế: `-Xlint:varargs` vẫn có thể phát cảnh báo **trong thân** một phương thức đã gắn `@SafeVarargs` nếu mảng được truyền tới một API khác hoặc có code khiến compiler nghi ngờ. Annotation không phải “tắt mọi cảnh báo”. Tốt nhất là chứng minh được hợp đồng của helper; khi không cần truyền cả mảng, lặp từng phần tử và copy tường minh như `snapshot` thường dễ review hơn.

### 6.3. Vì sao `@SuppressWarnings("unchecked")` không thay thế việc review?

`@SuppressWarnings("unchecked")` có phạm vi cảnh báo tương đối **cục bộ**; `@SafeVarargs` có thể làm mất cảnh báo ở cả call site. Cả hai chỉ ảnh hưởng quá trình báo warning, không khiến một `List<Integer>` trở thành `List<String>` thật.

Hạn chế suppress trên cả class hoặc package. Nếu có một phép chuyển đổi unchecked không thể tránh, hãy cô lập nó trong một helper nhỏ, ghi rõ điều kiện bảo đảm kiểu và test đường đi thất bại. Nếu method thực hiện alias/ghi sai mảng, **sửa code trước**, đừng dùng annotation làm cách tránh review.

## 7. Bài thử lỗi biên dịch: `@SafeVarargs` không hợp lệ trên method có thể override

Tạo **file riêng** `src/main/java/demo/InvalidAnnotation.java`:

~~~java
package demo;

import java.util.List;

public class InvalidAnnotation {
    @SafeVarargs
    public <T> void notFinal(List<T>... batches) {
        System.out.println(batches.length);
    }
}
~~~

Đây là **negative compile test**, không biên dịch chung với file hợp lệ phía trên. Chạy:

~~~sh
javac --release 21 -encoding UTF-8 -d out src/main/java/demo/InvalidAnnotation.java
~~~

Trình biên dịch Java 21 phải trả mã khác 0; thông báo chính:

~~~text
error: Invalid SafeVarargs annotation. Instance method <T>notFinal(List<T>...) is neither final nor private.
~~~

Lý do: phương thức `notFinal` là instance method có thể bị override; `@SafeVarargs` không phù hợp vì cam kết an toàn của lớp cha không được kiểm soát khi implementation bị ghi đè. Để hợp lệ, cần thiết kế method `final` hoặc `private` (nếu phù hợp về API), hoặc chuyển sang `static`. **Không tự đổi visibility/finality chỉ để tắt warning** nếu làm sai hợp đồng kế thừa mà code đang cần.

Lưu ý: lỗi này là **lỗi compile-time về vị trí annotation**, khác với heap pollution runtime do `poisonArray`. Mã bị compiler từ chối không được thực thi, và tên file/dòng trong diagnostic có thể khác vị trí mô tả ở trên.

## 8. Quy trình review theo từng bước

Khi nhận một method kiểu `method(List<T>... values)`, có thể dùng quy trình sau thay vì chỉ tìm `@SafeVarargs`:

### Bước 1 — Xác định kiểu phần tử có non-reifiable không

Các ví dụ cần quan tâm: `T...`, `List<String>...`, `List<? extends Number>...`. Không đánh đồng với `int...` hay `String...` có kiểu phần tử reifiable.

Đọc chữ ký method và các generic bounds; compiler có thể tạo mảng với component runtime thiếu thông tin của type argument. Bật `-Xlint:unchecked` hoặc `-Xlint:all` để thấy các chỗ cần xác minh.

### Bước 2 — Xác định *ownership* của mảng đầu vào

Caller có thể viết `f(a, b)` khiến compiler tạo mảng, hoặc `f(existingArray)` để truyền **chính mảng có sẵn** (nếu kiểu phù hợp). Không suy đoán rằng mảng trong method luôn mới và chỉ method có thể nhìn thấy nó.

Nếu code sửa mảng, hãy kiểm tra người gọi có quyền trông đợi nó không bị thay đổi hay không. Kể cả `String...`, mutation vẫn có thể ảnh hưởng caller.

### Bước 3 — Tìm toàn bộ đường ghi

Tìm phép gán chỉ số, alias `Object[]`, raw/unchecked conversion, reflection, `Arrays.fill`, `System.arraycopy`, method khác nhận mảng hoặc thành phần mảng. Xét **kiểu thực sự của đối tượng được ghi**, không chỉ kiểu khai báo của biến địa phương.

Ghi phần tử cùng kiểu có thể **type-safe nhưng không phù hợp hợp đồng bất biến**; ghi phần tử sai generic type qua alias có thể gây **heap pollution**. Không gộp hai nhận định thành một.

### Bước 4 — Tìm toàn bộ đường thoát

Kiểm tra `return values`, gán field, giữ trong collection backed by array, capture trong lambda/task, gửi cho callback/visitor hoặc helper có thể lưu array. Khi một tham chiếu đã thoát, có thể rất khó chứng minh mọi đoạn code khác không bao giờ thay nội dung.

Nếu không cần public array, trả **kết quả mới** hoặc immutable snapshot phù hợp; nếu cần giữ một cấu trúc, sao chép dữ liệu với mức độ sâu đúng mục tiêu.

### Bước 5 — Kiểm tra API/helper được gọi

Không mặc định mọi helper chỉ đọc. Nếu code chuyển mảng vào `Arrays.asList(values)`, nhớ đây là **backed view**; nếu view thoát ra ngoài, quyền sửa ô mảng cũng thoát. Nếu code gọi một API khác, đọc contract của nó: có giữ lại tham chiếu, mutate hoặc chạy bất đồng bộ không?

### Bước 6 — Chứng minh đủ điều kiện `@SafeVarargs`

Chỉ gắn annotation khi method/constructor hợp lệ **và** implementation thực sự không thực hiện hành vi nguy hiểm. Cân nhắc case mảng rỗng, phần tử `null`, phần tử immutable/mutable, mảng có sẵn, xử lý ngoại lệ và generic bounds.

Với `List.copyOf`, nhớ API **từ chối `null`**. Nếu hợp đồng cho phép null, cần một cách copy khác thích hợp thay vì giả định copy thành công trong mọi trường hợp.

### Bước 7 — Kiểm thử và kiểm tra cảnh báo trong CI

Viết một positive test cho đường đi an toàn. Với code nghi ngờ pollution, viết một test riêng minh họa điều kiện failure mà không đưa hành vi sai vào production. So sánh output/error thật. Nếu cảnh báo biến mất sau `@SafeVarargs`, vẫn review logic ở method; **không coi việc build sạch là bằng chứng an toàn**.

## 9. Ma trận quyết định khi nhìn thấy code đáng nghi

| Phát hiện | Đánh giá | Hành động phù hợp |
| --- | --- | --- |
| Lặp `for (T value : values)` để đọc và tạo collection mới | Thường an toàn, nếu không escape array và không ghi sai | Kiểm tra từng helper rồi cân nhắc `@SafeVarargs` |
| `values[0] = compatibleValue` | Có mutation mảng, chưa chắc heap pollution | Xem contract và liệu caller có truyền mảng sẵn |
| `Object[] x = values; x[0] = incompatibleValue` | Nguy cơ heap pollution rõ ràng | Xóa đường ghi sai, bỏ alias hoặc đổi thiết kế |
| `return values` | Escape trực tiếp | Trả copy/collection khác nếu không chủ ý chuyển quyền quản lý |
| `this.values = values` | Escape qua field | Copy và quản lý quyền sở hữu |
| `return Arrays.asList(values)` | Escape qua view backed by array | Trả snapshot nếu cần cách ly |
| `callback.accept(values)` | Chưa đủ thông tin | Đọc hợp đồng callback, có mutate/retain hay không |
| `@SafeVarargs` trên code ghi sai | Cam kết không đúng, warning có thể bị che | Sửa code, không chỉ thay annotation |
| `String... values` ghi đúng String | Không phải heap pollution generic, vẫn có side effect | Kiểm tra caller-provided array |
| `List.copyOf(...)` | Snapshot cấu trúc collection, unmodifiable | Kiểm tra `null` và object mutable bên trong |

## 10. Tự luyện và đáp án

**Câu 1.** Tại sao `return batches;` từ `List<String>... batches` lại là điểm đáng chú ý dù thân phương thức không sửa mảng?

**Đáp án:** Nó làm mảng thoát khỏi method. Caller hoặc helper khác có thể alias nó qua `Object[]` rồi đặt `List<Integer>` vào một ô mảng; về sau lời hứa `List<String>[]` bị phá vỡ. Bản thân việc trả về không bắt buộc đã gây pollution ngay lúc trả, nhưng nó mở ra đường ghi khó kiểm soát.

**Câu 2.** `Arrays.asList(batches)` có phải một bản sao tách biệt khỏi mảng không?

**Đáp án:** Không. List do `Arrays.asList` tạo là **fixed-size view backed by the original array**. `set` có thể làm thay mảng gốc, dù `add`/`remove` không đổi được số lượng phần tử.

**Câu 3.** Vì sao `List.copyOf(Arrays.asList(batches))` khác với `Arrays.asList(batches)`?

**Đáp án:** `List.copyOf` tạo một kết quả unmodifiable theo hợp đồng và không công bố mảng varargs như backing mutable view. Tuy nhiên, copy chỉ ở cấp collection ngoài và có thể giữ tham chiếu tới các list/đối tượng con. Compiler cũng có thể cảnh báo `-Xlint:varargs` về việc truyền mảng sang helper; lặp/copy rõ như `snapshot` dễ review hơn.

**Câu 4.** Nếu `String[] values = {"old"}; modifyCaller(values);` rồi in `values[0]`, chuyện gì xảy ra? Có phải heap pollution không?

**Đáp án:** Sau lời gọi, `values[0]` là `"modified"`; caller đã truyền một mảng có sẵn. Đây là side effect có thể gây bug, nhưng không phải heap pollution generic vì vẫn là giá trị `String` phù hợp.

**Câu 5.** Method có `List<String>...` chỉ đọc dữ liệu, không alias/ghi mảng, và tạo kết quả mới. Có chắc chắn cần loại bỏ varargs không?

**Đáp án:** Không. Generic varargs có rủi ro cần kiểm tra, nhưng một implementation read-only có thể an toàn. Nếu thiết kế varargs mang lại ích lợi rõ ràng và method đáp ứng điều kiện, `@SafeVarargs` là cách biểu diễn cam kết của tác giả.

**Câu 6.** Có thể đặt `@SafeVarargs` lên mọi public instance method có `List<T>...` để giảm warnings không?

**Đáp án:** Không. Method instance có thể override mà không phải `final`/`private` không hợp lệ với `@SafeVarargs`. Ngoài ra, annotation chỉ đúng khi implementation thực sự không có thao tác unsafe.

**Câu 7.** Khi method có lệnh `batches[0].add("x")`, đây có phải thao tác ghi vào ô `batches[0]` không?

**Đáp án:** Không: nó thay **nội dung List** mà ô mảng đang tham chiếu, chứ không thay tham chiếu trong ô mảng. Tuy nhiên, nếu caller dùng cùng List, dữ liệu caller có thể bị sửa; nếu List là unmodifiable, `add` có thể ném `UnsupportedOperationException`. Đây vẫn là đường mutation cần audit.

## 11. Checklist áp dụng trong code review

- [ ] Đánh dấu các varargs element type non-reifiable: `T...`, `List<T>...`, `List<String>...`.
- [ ] Biết compiler có thể tạo mảng hoặc caller có thể truyền mảng hiện hữu.
- [ ] Tìm mọi thao tác viết tới ô mảng, cả trực tiếp và qua `Object[]`/raw alias.
- [ ] Phân biệt mutation ô mảng với mutation đối tượng bên trong ô.
- [ ] Tìm mọi đường return, field store, callback, lambda, backed view hoặc API helper có thể làm **mảng thoát**.
- [ ] Xác định rõ bất biến, ownership, lifetime, kiểu generic của các giá trị được ghi.
- [ ] Ưu tiên tạo kết quả/immutable snapshot mới nếu không cần công bố mảng; kiểm tra nested mutable elements và `null`.
- [ ] Kiểm tra `@SafeVarargs` đúng loại method/constructor, không dùng annotation che hành vi sai.
- [ ] Bật `javac -Xlint:all`; xử lý cảnh báo bằng code review có lý do, không suppress cả module.
- [ ] Chạy test có cả đường đi an toàn và đường đi cố ý gây lỗi trong môi trường độc lập.
- [ ] Không đánh đồng `ClassCastException` với thời điểm heap pollution bắt đầu.
- [ ] Khi đổi API sang collection, giữ đúng hợp đồng dữ liệu và mức độ copy cần thiết.

## 12. Tài liệu chính thức (còn hiệu lực với Java hiện đại)

- [Java Language Specification SE 21 `8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.1): varargs là array parameter; cảnh báo unchecked với element type non-reifiable.
- [JLS SE 21 `9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.7): ý nghĩa annotation, hạn chế vị trí dùng và tác động đến warnings.
- [JLS SE 21 `4.12.2 — Heap Pollution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.2): tham chiếu generic bị rơi khỏi hợp đồng type parameter.
- [Javadoc Java SE 21 — SafeVarargs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/SafeVarargs.html): ví dụ alias `Object[]` gây `ClassCastException` dù có annotation.
- [Javadoc Java SE 21 — Arrays.asList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)): list kích thước cố định và được backed by array.
- [Javadoc Java SE 21 — List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): tạo list unmodifiable và yêu cầu không có `null`.

**Kết luận:** Với generic varargs, hỏi **“ai có thể ghi ô mảng?”** và **“mảng có thoát ra ngoài không?”** trước khi tin vào `@SafeVarargs`. Không phải mọi mutation đều là heap pollution, nhưng mỗi đường ghi và escape phải được giải thích bằng kiểu dữ liệu, hợp đồng API và quyền sở hữu cụ thể. Những cách thiết kế này tiếp tục áp dụng trên JDK được hỗ trợ hiện nay, không cần dựa vào API legacy.
