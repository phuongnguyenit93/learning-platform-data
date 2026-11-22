# Phân biệt xóa kiểu (type erasure) với tạo lớp chuyên biệt cho từng đối số kiểu

Khi gặp `Box<String>`, `Box<Integer>`, `List<String>` hoặc `List<Integer>`, ta có thể hình dung hai cách triển khai generics:

- **Xóa kiểu (type erasure):** trình biên dịch kiểm tra các đối số kiểu ở mã nguồn rồi biên dịch thành mã sử dụng kiểu đã xóa; những cách dùng khác nhau của cùng một khai báo lớp generic thường chia sẻ **cùng lớp runtime**.
- **Tạo lớp chuyên biệt cho từng đối số kiểu (specialization/monomorphization):** hệ thống biên dịch hoặc thực thi có thể tạo một dạng thực thi riêng cho mỗi tổ hợp kiểu cụ thể, chẳng hạn một phiên bản chuyên biệt cho `String` và một phiên bản cho `Integer`. Đây là mô hình để đối chiếu, **không phải hành vi mặc định của Java generics thông thường**.

Khác biệt quan trọng nằm ở việc **kiểu cụ thể ảnh hưởng thế nào đến mã thực thi và cách biểu diễn dữ liệu**. Java chủ yếu dùng erasure để hiện thực hóa generics ở bytecode. Đừng đồng nhất việc nhiều kiểu generic được kiểm tra khác nhau ở nguồn với việc JVM phải có bấy nhiêu lớp chuyên biệt.

## 1. Cùng một khai báo generic, hai hướng triển khai

Giả sử ta định nghĩa:

```java
// Snippet mô tả khai báo; đoạn chạy đầy đủ ở mục 6.
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Và sử dụng:

```java
Box<String> greeting = new Box<>("Java");
Box<Integer> number = new Box<>(42);
```

Ở **cấp mã nguồn**, trình biên dịch biết `greeting.get()` có kiểu `String`, còn `number.get()` có kiểu `Integer`. Bởi vậy, lệnh `String s = number.get();` bị từ chối khi biên dịch. Song điều đó chưa cho biết JVM lưu bao nhiêu định nghĩa lớp.

### Hướng A — xóa kiểu như Java sử dụng

Vì `T` không có giới hạn trên tường minh, erasure của `T` là `Object`. Có thể hình dung dạng tương đương ở tầng descriptor như sau:

```java
// Pseudocode giải thích erasure, không phải mã Java cần khai báo thêm.
class Box {
    private final Object value;

    Box(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

Đây là **mô hình diễn giải**: javac thực sự tạo bytecode, không sinh tệp `Box.java` mới theo cách minh họa. Có một định nghĩa lớp `Box` dùng cho cả hai cách gắn kiểu, và compiler có thể chèn cast `String` hoặc `Integer` ở nơi nhận kết quả.

```text
Nguồn Java:
  Box<String>         Box<Integer>
        \                  /
         \                /
          v              v
       cùng class runtime Box
        field value: Object
        method get(): Object
```

### Hướng B — giả định tạo dạng chuyên biệt theo kiểu

Một hệ thống chọn specialization có thể tạo hai phiên bản tương đương về ý nghĩa:

```java
// Pseudocode: minh họa chiến lược chuyên biệt hóa.
// Đây KHÔNG phải hai lớp do javac tự sinh từ Box<T>.
final class BoxForString {
    private final String value;
    BoxForString(String value) { this.value = value; }
    String get() { return value; }
}

final class BoxForInteger {
    private final Integer value;
    BoxForInteger(Integer value) { this.value = value; }
    Integer get() { return value; }
}
```

Theo giả định này, việc sử dụng `Box<String>` và `Box<Integer>` có hai dạng thực thi riêng, có thể chứa thao tác đọc trường, chữ ký và tối ưu hóa khác nhau. Nhưng **specialization không nhất thiết luôn có nghĩa tạo tệp `.class` hoặc lớp được đặt tên riêng**; tùy thiết kế ngôn ngữ, runtime có thể phát sinh các dạng mã chuyên biệt hoặc tái sử dụng một phần mã thực thi. Ví dụ trên cố ý chọn cách “tạo lớp riêng” để thấy rõ sự đối lập.

## 2. Bảng so sánh trực tiếp

| Khía cạnh | Type erasure của Java generics thông thường | Mô hình tạo dạng chuyên biệt theo đối số kiểu |
| --- | --- | --- |
| Sau khi kiểm tra kiểu nguồn | Xóa các tham số kiểu khỏi descriptor thông thường, dùng bound hoặc `Object` | Có thể tạo dạng thực thi với kiểu cụ thể |
| `Box<String>` và `Box<Integer>` | Cùng lớp runtime `Box` | Có thể ánh xạ tới hai dạng chuyên biệt |
| Kiểu trường `T value` | `Object` khi `T` không bound | Có thể dùng `String` và `Integer` trong từng dạng |
| Kiểu trả về `T get()` | Descriptor trả `Object`; nơi gọi có thể cần cast | Có thể có chữ ký/đường chạy cụ thể tương ứng |
| Lượng mã phải sinh | Không nhân số lượng class theo mọi cách gắn kiểu | Có thể tăng theo số trường hợp chuyên biệt |
| Runtime biết đối số kiểu? | Không có type argument cụ thể gắn trực tiếp vào mỗi instance generic thông thường | Tùy thiết kế; chuyên biệt hóa và phản chiếu kiểu là hai đặc tính khác nhau |
| Kiểu nguyên thủy trong Java | `List<int>` không hợp lệ; dùng `List<Integer>` với boxing/unboxing | Một thiết kế chuyên biệt có thể hỗ trợ giá trị nguyên thủy trực tiếp nếu ngôn ngữ cho phép |
| Tương thích thư viện Java cũ | Erasure được chọn để hỗ trợ việc đưa generics vào hệ sinh thái bytecode cũ | Cần chiến lược tương thích riêng; không tự bảo đảm giữ nguyên descriptor cũ |
| Chi phí tại runtime | Một dạng class phổ biến; cast, boxing và dispatch có chi phí tùy ngữ cảnh | Có thể giảm một số chi phí nhưng có nguy cơ tăng code size và áp lực cache |
| An toàn kiểu mã nguồn | Compiler kiểm tra generics | Compiler cũng có thể kiểm tra generics; chiến lược thực thi không quyết định một mình tính an toàn |

Lưu ý: cột thứ hai nói về **thiết kế generic của Java hiện hành**, còn cột thứ ba là **mô hình triển khai giả định** dùng để phân biệt khái niệm. Không nên dùng bảng để kết luận mọi ngôn ngữ có specialization đều sinh một bản class cho mọi đối số kiểu.

## 3. Java xóa kiểu chính xác như thế nào?

Trước khi so sánh hai chiến lược, cần xác định chính xác **phần nào của Java bị erasure**:

| Source-level form | Kiểu thường dùng ở JVM descriptor | Có tạo class mới theo `T`? |
| --- | --- | --- |
| `T` không bound | `Object` | Không |
| `T extends Number` | `Number` | Không |
| `T extends Number & Comparable<T>` | `Number` (first bound) | Không |
| `List<String>` | `List` | Không |
| `T[]` | Mảng của erasure của `T` | Không |
| `List<T>` trong method parameter | `List` | Không |

Compiler kiểm tra các generic relationships **trước** erasure, có thể chèn `checkcast` khi caller đọc dữ liệu và sinh **bridge method** khi cần bảo toàn overriding. Các cơ chế ấy không đồng nghĩa specialization: bridge xử lý liên kết/dispatch, cast kiểm tra giá trị ở chỗ sử dụng; không cơ chế nào biến `Box<Integer>` thành primitive `Box<int>`.

Bài riêng về **type variable bounds**, **method/array descriptors** và **checkcast** đã mô tả từng quy tắc. Ở đây chúng được đặt chung để đánh giá sự khác biệt giữa một binary generic **dùng chung** và các bản implementation chuyên biệt.

## 4. Vì sao Java chọn erasure thay vì tạo một lớp cho từng đối số kiểu?

Khi Java 5 bổ sung generics, `List`, `Collection` và nhiều thư viện cũ đã tồn tại. **Migration compatibility** là một lý do lớn để chọn erasure: API generic hóa nhiều khi vẫn giữ **cùng erased JVM method descriptors**, để class đã biên dịch và mã nguồn cũ có thể từng bước chuyển sang generic form.

```java
// Mô hình đối chiếu hai phiên bản nguồn của API:
void accept(java.util.List values) {}          // API cũ kiểu raw
// void accept(java.util.List<String> values) {} // Dạng generic hóa
```

Hai chữ ký trên **không thể cùng là overload** của một class vì cùng erasure; chúng minh họa lựa chọn giữa hai cách khai báo API. Erasure không bảo đảm mọi thay đổi source/binary đều tương thích tuyệt đối: inheritance, overload, generic `Signature`, bridge, runtime class-file version và semantics API vẫn phải kiểm tra. Sự đánh đổi với specialization là **số lượng artifacts/code versions** và khả năng tối ưu riêng từng representation.

## 5. Cùng runtime class không có nghĩa hai kiểu generic gán được cho nhau

Java coi `Box<String>` và `Box<Integer>` là hai cách gắn tham số **khác nhau về kiểu tĩnh**. Erasure là cơ chế thực thi, không xóa quy tắc gán kiểu của javac.

```java
// Snippet minh họa, không phải một chương trình độc lập:
List<String> names = new java.util.ArrayList<>();
List<Integer> ids = new java.util.ArrayList<>();

// names = ids;             // Không biên dịch
// List<Object> all = names; // Cũng không biên dịch
```

Generics thông thường trong Java **bất biến**: `List<String>` không phải subtype của `List<Object>` dù `String` là subtype của `Object`. Có thể dùng wildcard `List<? extends Object>` khi chỉ cần đọc đối tượng ở mức `Object`, hoặc `List<? super String>` khi API cần nhận các phần tử `String` theo hướng phù hợp.

Hai dòng `new ArrayList<>()` phía trên có cùng runtime class **vì cùng chọn triển khai `ArrayList`**. Nhưng một `ArrayList<String>` và `LinkedList<String>` có runtime class khác nhau vì bản thân **triển khai collection khác nhau**, không liên quan chuyện đối số kiểu bằng nhau.

## 6. Chương trình Java 17+ chứng minh sự khác biệt

Lưu mã sau trong tệp **`ErasureVsSpecializationDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ErasureVsSpecializationDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class NumberBox<N extends Number> {
        private final N value;

        NumberBox(N value) {
            this.value = value;
        }

        N get() {
            return value;
        }
    }

    static class Holder<T> {
        private T value;

        void set(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class StringHolder extends Holder<String> {
        @Override
        void set(String value) {
            super.set(value);
        }
    }

    static final class Counter<T> {
        static int created;

        Counter() {
            created++;
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Box<String> stringBox = new Box<>("Java");
        Box<Integer> integerBox = new Box<>(42);
        List<String> texts = new ArrayList<>();
        List<Integer> ids = new ArrayList<>();

        System.out.println("Box<String> va Box<Integer> cung class: "
                + (stringBox.getClass() == integerBox.getClass()));
        System.out.println("ArrayList<String> va ArrayList<Integer> cung class: "
                + (texts.getClass() == ids.getClass()));

        Method boxGet = Box.class.getDeclaredMethod("get");
        System.out.println("Kieu tra ve da xoa cua Box.get: "
                + boxGet.getReturnType().getSimpleName());
        System.out.println("Kieu tra ve generic cua Box.get: "
                + boxGet.getGenericReturnType().getTypeName());
        System.out.println("Kieu tra ve da xoa cua NumberBox.get: "
                + NumberBox.class.getDeclaredMethod("get").getReturnType()
                    .getSimpleName());

        String text = stringBox.get();
        System.out.println("Gia tri String: " + text);

        Holder<String> holder = new StringHolder();
        holder.set("bridge");
        System.out.println("Gia tri qua Holder<String>: " + holder.get());
        System.out.println("StringHolder co bridge: "
                + Arrays.stream(StringHolder.class.getDeclaredMethods())
                    .anyMatch(Method::isBridge));

        new Counter<String>();
        new Counter<Integer>();
        System.out.println("Counter.created dung chung: " + Counter.created);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ErasureVsSpecializationDemo.java
java ErasureVsSpecializationDemo
```

Đầu ra:

```text
Box<String> va Box<Integer> cung class: true
ArrayList<String> va ArrayList<Integer> cung class: true
Kieu tra ve da xoa cua Box.get: Object
Kieu tra ve generic cua Box.get: T
Kieu tra ve da xoa cua NumberBox.get: Number
Gia tri String: Java
Gia tri qua Holder<String>: bridge
StringHolder co bridge: true
Counter.created dung chung: 2
```

Kết quả đã được đối chiếu bằng cách chạy các lớp và phương thức tương đương trong JDK với cú pháp tương thích Java 17. Giải thích từng điểm:

1. **Hai `Box` dùng cùng class:** `getClass()` so sánh hai `Class` object đại diện cùng khai báo runtime `Box`. Nếu Java tự sinh lớp riêng cho mỗi `T`, phép so sánh này sẽ không phản ánh mô hình dùng chung như ở đây.
2. **Hai `ArrayList` cùng class:** khác biệt `String`/`Integer` là thông tin kiểu ở nguồn; bản thân `ArrayList` được dùng chung.
3. **`Box.get` trả về `Object` trong reflection thông thường:** method descriptor là dạng đã xóa `T` không bound. `getGenericReturnType()` đọc được metadata cho biết khai báo gốc có type variable `T`. Nó **không** tự trả về `String` của riêng biến `stringBox`.
4. **`NumberBox.get` trả về `Number`:** giới hạn `N extends Number` quyết định erasure, cho thấy “xóa kiểu” không luôn có nghĩa thay tất cả bằng `Object`.
5. **Đọc `String` vẫn an toàn ở mã nguồn:** trình biên dịch đã kiểm tra `Box<String>`; nếu cần cast, cast diễn ra ở nơi thích hợp. Đây không phải lớp `BoxForString` riêng.
6. **Bridge method có thật:** `StringHolder` là một **lớp con do lập trình viên khai báo rõ**; bridge bảo toàn override sau erasure của `Holder<T>`. Cờ `isBridge()` không chứng minh có specialization theo tham số kiểu.
7. **Biến static được dùng chung:** `Counter<String>` và `Counter<Integer>` dùng một trường `Counter.created`, nên sau hai lần tạo đối tượng giá trị là 2. Trong cùng một class được tải bởi cùng class loader, mỗi lần gắn type argument không tạo bộ static field riêng.

Để quan sát sâu hơn, sau khi biên dịch hãy chạy:

```bash
javap -p -s 'ErasureVsSpecializationDemo$Box'
javap -p -s 'ErasureVsSpecializationDemo$NumberBox'
javap -p -v 'ErasureVsSpecializationDemo$StringHolder'
```

Những lệnh này xem descriptor `Object`/`Number`, metadata `Signature` và phương thức bridge trong bytecode. Tên lớp lồng nhau có dấu `$`; dùng dấu nháy để shell không diễn giải ký tự này ngoài ý muốn. Phiên bản javap có thể trình bày các thuộc tính phụ khác nhau, nhưng ý nghĩa của descriptor và bridge là như nhau.

## 7. “Một lớp dùng chung” có thật sự không còn thông tin generic nào?

Không. Một binary generic dùng chung vẫn có thể chứa thuộc tính `Signature` mô tả **khai báo**: type parameters, bounds, generic superclasses, fields và methods. Reflection như `Box.class.getTypeParameters()` có thể đọc tên `T`; một subclass khai báo `extends Box<String>` có thể lưu đối số `String` trên **kiểu cha**.

Điều nó không tự có là **actual type argument riêng của mỗi instance `new Box<T>()`**. `getClass()` trả class runtime chung; nếu cần xác minh kiểu bên ngoài API, hãy nhận `Class<T>` token hoặc metadata khác một cách có chủ đích. Bài cuối chương về `Signature` minh họa đầy đủ descriptor, field/method metadata và `TypeVariable`/`ParameterizedType`.

## 8. Erasure, specialization và reification là ba khái niệm liên quan nhưng khác nhau

**Erasure** nói tới cách diễn đạt/biên dịch khai báo generic: tham số kiểu được thay bằng các kiểu đã xóa trong descriptor thường và mã được chia sẻ. **Specialization** nói tới khả năng tạo những dạng thực thi riêng cho các tổ hợp kiểu. **Reification** nói tới mức độ thông tin kiểu có mặt để runtime có thể quan sát hoặc kiểm tra.

Chẳng hạn:

- Mảng Java như `String[]` có runtime component type, nên `Object[] array = new String[1]; array[0] = 123;` ném `ArrayStoreException` khi chạy (giả sử đặt trong một khối Java hợp lệ). Kiểu thành phần của array mang thông tin runtime cần thiết.
- `List<String>` **không phải kiểu reifiable** để kiểm tra bằng `instanceof List<String>`. Có thể kiểm tra `instanceof List<?>` vì wildcard không buộc JVM xác minh loại phần tử.
- Một hệ thống có thể lưu type argument ở runtime mà không nhất thiết tạo bản sao hoàn toàn của mọi đoạn mã generic. Ngược lại, tạo mã chuyên biệt có thể phục vụ tối ưu hóa mà không tự động hứa cung cấp đầy đủ API reflection của mọi type argument.

Vì vậy, đừng định nghĩa specialization đơn giản là “runtime biết generic” hoặc erasure đơn giản là “runtime không còn phân biệt String với Integer”. Cần hỏi chính xác: **runtime phân biệt cái gì, ở lớp đối tượng nào và bằng cơ chế nào?**

## 9. Những hệ quả dễ thấy của erasure trong Java

Từ việc binary generic dùng chung, những hạn chế hay gặp là:

- Không thể overload chỉ theo `List<String>` và `List<Integer>` vì erased method descriptors trùng nhau.
- Không dùng `instanceof List<String>` để kiểm tra mọi element ở runtime; `List<?>` chỉ kiểm tra class.
- Không trực tiếp viết `new T()`, `T.class`, `new T[n]` cho type variable không reifiable.
- Raw/unchecked APIs có thể tạo heap pollution, khiến cast ở một lời gọi khác thất bại.
- Java generics reference thông thường không chấp nhận `List<int>`; `List<Integer>` không đồng nghĩa representation primitive.

Những giới hạn này **không chứng minh** specialization luôn tốt hơn: nó có thể cải thiện một số đường xử lý primitive nhưng cũng tăng code size hoặc complexity. Hãy so sánh bằng mục tiêu representation và số liệu workload, không chỉ bằng tên cơ chế. Đối với code riêng cần primitive field, có thể định nghĩa `IntBox` tường minh; đó là **thiết kế API thủ công**, không phải generic specialization tự động.

## 10. Chi phí bộ nhớ và hiệu năng: vì sao không có chiến lược luôn thắng?

Có hai loại chi phí khác nhau:

**Số lượng phiên bản mã:** nếu tạo thực thi riêng cho rất nhiều tổ hợp kiểu (`Box<Customer>`, `Box<Order>`, `Box<Product>`, v.v.), code size có thể tăng. Nhiều bản mã có thể làm tăng thời gian biên dịch hoặc tải mã, dùng thêm bộ nhớ mã và ảnh hưởng instruction cache. Erasure tạo ít biến thể class hơn, thường thuận lợi cho dùng lại thư viện.

**Biểu diễn dữ liệu và thao tác:** dạng chung chứa `Object` có thể cần cast; khi generic nhận wrapper cho primitive, boxing/unboxing và cấp phát có thể ảnh hưởng hiệu năng. Dạng chuyên biệt cho dữ liệu thích hợp có thể giảm những chi phí đó, cải thiện locality và tối ưu trực tiếp theo kiểu.

Tuy nhiên, **không nên kết luận** “erasure luôn nhanh hơn vì ít class” hoặc “specialization luôn nhanh hơn vì bỏ cast”. HotSpot JVM có JIT, profile, inline, escape analysis và những tối ưu khác. Nó có thể tạo các đường mã máy hiệu quả cho các kiểu thực tế đang chạy mà **không tạo lớp Java mới `BoxForString` cho mỗi type argument**. Cũng có phép cast rất rẻ hoặc bị tối ưu đi.

Ví dụ, `String` và `Integer` trong hai `Box` không khiến trường `Object` phải lưu “chuỗi đã xóa” hay “số nguyên đã xóa”; nó giữ tham chiếu đến các đối tượng thực. Đo benchmark hợp lệ cần kiểm soát warm-up, JIT, allocation, loại workload và sử dụng công cụ như JMH; không thể chỉ dựa vào cơ chế generic để dự đoán thời gian chạy.

## 11. Có thể tự tạo lớp riêng cho từng kiểu trong Java không?

Có, nhưng đây là **quyết định lập trình API**, không phải automatic specialization của `Box<T>`:

```java
// Snippet thiết kế hai lớp riêng; độc lập với cơ chế erasure của Box<T>.
final class StringBox {
    private final String value;
    StringBox(String value) { this.value = value; }
    String get() { return value; }
}

final class IntBox {
    private final int value;
    IntBox(int value) { this.value = value; }
    int get() { return value; }
}
```

Hai lớp này có hai runtime classes thực sự. `IntBox` chứa trường `int` chứ không cần `Integer`; đây là sự chuyên biệt **do lập trình viên viết bằng tay**. Nếu cần nhiều kiểu, có thể phát sinh một lượng code trùng lặp lớn. Đây cũng là lý do thư viện Java cung cấp các API chuyên cho primitive trong những trường hợp nhất định, ví dụ `IntStream`, `LongStream`, `DoubleStream`, bên cạnh `Stream<T>`.

Hãy phân biệt rõ:

- `Box<String>` và `Box<Integer>` theo cùng khai báo `Box<T>`: **một class generic bị erasure**.
- `StringBox` và `IntBox` do tự khai báo: **hai class khác nhau** với kiểu trường có thể khác.
- `StringHolder extends Holder<String>`: **một subclass thực do lập trình viên viết**, nhưng `Holder<T>` vẫn không được nhân thành `Holder<String>` và `Holder<Integer>` riêng.
- Mã máy mà JIT tối ưu hóa theo kiểu runtime: có thể có **mã máy chuyên biệt cho đường chạy**, nhưng điều đó không đồng nghĩa JVM giới thiệu class generic Java mới cho mỗi `T`.

Đừng lấy việc tồn tại một subclass riêng hoặc mã JIT riêng làm bằng chứng compiler Java đã chuyển từ erasure sang monomorphization của khai báo generic ban đầu.

## 12. Bài tập tư duy: chọn nhận định đúng

**Tình huống A.** Hai biến `List<String>` và `List<Integer>` được khởi tạo bằng `new ArrayList<>()`. Có thể kết luận gì?

Có thể kết luận runtime class đều là `ArrayList`. Không thể kết luận chúng gán được cho nhau; compiler vẫn biết đối số kiểu khác nhau ở nguồn.

**Tình huống B.** Một đối tượng của `class Data<T extends Number>` có `T data;`. Sau erasure, kiểu trường trong descriptor thường là gì?

Là `Number`, không phải `Object` và không được tự động chọn `Integer` chỉ vì ở một nơi ta viết `Data<Integer>`.

**Tình huống C.** Reflection trả về `T` khi gọi `getGenericReturnType()`. Có phải runtime đang giữ kiểu `T = String` cho từng instance?

Không. Reflection đang đọc **khai báo generic**; object `Box<String>` thông thường không có class runtime riêng chứa `String` làm tham số cho chính class ấy.

**Tình huống D.** Một phương thức bridge `set(Object)` xuất hiện trong lớp con `StringHolder`. Có chứng minh compiler tạo specialization cho `Holder<String>` không?

Không. Bridge được tạo để **bảo toàn ghi đè** khi phương thức generic bị xóa kiểu.

**Tình huống E.** Một bộ biên dịch chọn tạo mã máy riêng cho `int` và `double`. Có đồng nghĩa nó chắc chắn tạo hai lớp Java được nhìn thấy qua `Class` không?

Không nhất thiết. Dạng mã thực thi chuyên biệt, cấu trúc runtime class và khả năng reflection có thể được thiết kế độc lập ở những mức độ nhất định.

## 13. Checklist khi phân tích một API generic

Khi muốn biết một đoạn Java sử dụng erasure hay có lớp đặc thù, hãy kiểm tra theo thứ tự:

1. **Khai báo gốc là gì?** `class Box<T>` hay hai lớp `StringBox`, `IntBox` thật sự được định nghĩa?
2. **Bound của type parameter là gì?** `T` không bound xóa thành `Object`; `T extends Number` xóa thành `Number`.
3. **Đối số kiểu có tạo class riêng không?** Đừng đoán từ cú pháp `<String>`. Dùng `getClass()` để quan sát runtime class của các đối tượng cùng generic class.
4. **Có cast hoặc bridge không?** Đây thường là dấu hiệu cơ chế giữ an toàn kiểu/đa hình với erasure, không phải class specialization.
5. **Runtime metadata có gì?** `getReturnType()` thể hiện kiểu đã xóa, `getGenericReturnType()` phản ánh khai báo có generic nếu metadata hiện diện.
6. **Bottleneck thật nằm ở đâu?** Kiểm tra boxing, allocation, dữ liệu và kết quả benchmark trước khi viết lớp chuyên biệt bằng tay.

**Kết luận cốt lõi:** trong Java generics thông thường, `Box<String>` và `Box<Integer>` là hai cách sử dụng có **kiểu tĩnh khác nhau** nhưng cùng **khai báo class runtime `Box`**. Type erasure thực hiện điều này bằng cách xóa tham số kiểu khỏi descriptor, thêm cast và bridge khi cần. Việc tạo lớp hoặc mã thực thi riêng cho từng đối số kiểu là một chiến lược specialization khác, có những cơ hội tối ưu và chi phí riêng; Java không tự động thực hiện chiến lược “mỗi `T` một class” chỉ vì ta dùng cú pháp generic.