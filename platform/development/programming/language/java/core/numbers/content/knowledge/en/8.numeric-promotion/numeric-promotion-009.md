# Overload: nâng kiểu primitive, boxing và giới hạn kết hợp trong Java

Khi một lớp có nhiều phương thức cùng tên nhưng khác danh sách tham số (**overload**), Java chọn chữ ký sẽ gọi **tại thời điểm biên dịch** theo kiểu tĩnh của đối số. Sự lựa chọn này phụ thuộc vào những phép chuyển kiểu được cho phép ở từng giai đoạn xét overload. Ba khái niệm quan trọng là **widening primitive** (mở rộng kiểu nguyên thủy), **boxing/unboxing** (đóng hộp/mở hộp) và giới hạn khi kết hợp chúng.

Sau bài này, bạn có thể dự đoán vì sao `m(7)` chọn `m(long)` thay vì `m(Integer)`; vì sao `int` không tự trở thành `Long`; và khi nào compiler ưu tiên một overload cố định thay vì varargs.

## 1. Hiểu ba nhóm chuyển kiểu

### Widening primitive

Widening primitive mở rộng một kiểu nguyên thủy sang kiểu có miền biểu diễn khác: `byte → short → int → long → float → double`; `char → int → long → float → double`; `short → int → long → float → double`. Không có chuyển đổi số tự động từ `boolean`; `char` không widening sang `short`.

~~~java
static void write(long value) { }

byte number = 7;
write(number); // byte -> long: hợp lệ
write(7);      // int -> long: hợp lệ
~~~

Widening primitive thường không mất phạm vi giá trị nhưng **có thể mất độ chính xác** với số lớn chuyển sang `float` hoặc `double`. Đây không phải narrowing primitive: `long → int` cần cast tường minh.

### Boxing và unboxing

Boxing đổi một giá trị primitive thành wrapper tương ứng, chẳng hạn `int → Integer`, `long → Long`, `byte → Byte`. Unboxing đổi ngược lại, như `Integer → int`. Wrapper là đối tượng và có thể bằng `null`; nếu unbox `null`, Java ném `NullPointerException` khi thực thi.

~~~java
static void takeInteger(Integer value) { }

takeInteger(7);         // boxing int -> Integer
Integer boxed = 7;     // boxing trong phép gán
int plain = boxed;     // unboxing Integer -> int
~~~

`Integer` và `Long` là hai class wrapper riêng, không có quan hệ kế thừa giữa chúng; truyền wrapper này cho tham số wrapper kia không phải là widening reference.

### Widening reference

`Integer → Number → Object` là các chuyển đổi mở rộng kiểu tham chiếu (widening reference). Chúng không cần unboxing.

~~~java
static void takeNumber(Number value) { }

Integer x = 7;
takeNumber(x); // Integer -> Number: widening reference
~~~

Nếu primitive `int` được truyền vào tham số `Object`, Java có thể **boxing `int → Integer` rồi widening reference `Integer → Object`**.

## 2. Java xét overload theo ba pha

Theo Java Language Specification `15.12.2, compiler tìm phương thức có thể áp dụng theo thứ tự sau:

| Pha | Khi nào áp dụng | Chuyển kiểu |
| --- | --- | --- |
| 1 — strict invocation | Số đối số cố định; không boxing/unboxing và không trải varargs | Khớp kiểu, widening primitive, widening reference |
| 2 — loose invocation | Nếu pha 1 không có ứng viên; vẫn số đối số cố định | Thêm boxing/unboxing và các chuỗi chuyển hợp lệ |
| 3 — variable arity | Nếu hai pha trước không có ứng viên | Gọi varargs bằng các đối số phần tử |

**Tìm được ứng viên ở pha nào thì dừng việc tìm pha sau ngay ở pha ấy.** Trong pha đang xét, nếu nhiều overload có thể áp dụng, Java chọn phương thức **cụ thể nhất** (most specific). Nếu không xác định được lựa chọn duy nhất, lỗi `ambiguous method call`; nếu không overload nào áp dụng, lỗi biên dịch.

Điều này giải thích khẩu quyết “widening trước boxing, boxing trước varargs” trong các ví dụ đơn giản. Tuy nhiên “thắng” ở đây nói về **pha xét tính áp dụng**; nó không thay thế quy tắc chọn phương thức cụ thể nhất khi nhiều chữ ký cùng pha cạnh tranh.

Một hàm khai báo `void f(int... values)` thực chất có tham số mảng `int[]`. Khi truyền một `int[]` vào hàm, nó được xét như lời gọi có số đối số cố định ngay pha 1; chỉ khi truyền các phần tử riêng lẻ để Java đóng gói mảng mới cần pha 3.

## 3. Vì sao `int` ưu tiên `long` hơn `Integer`?

~~~java
static String choose(long value) {
    return "long";
}
static String choose(Integer value) {
    return "Integer";
}
~~~

- `choose(7)`: literal `7` có kiểu `int`. `int → long` là widening primitive nên overload `long` áp dụng ở pha 1. `int → Integer` là boxing, chỉ đến pha 2 mới được xét. Chọn `long`.
- `byte b = 7; choose(b)`: `byte → long` là widening primitive ở pha 1. Không có boxing trực tiếp `byte → Integer`. Chọn `long`.
- `choose(Integer.valueOf(7))`: đối số có kiểu `Integer`. Overload `Integer` là khớp chính xác ở pha 1, còn `long` cần unboxing `Integer → int` rồi widening `int → long` ở pha 2. Chọn `Integer`.

Điều đáng ghi nhớ là **kiểu tĩnh của biểu thức đối số**, không chỉ giá trị bằng số. `7`, `7L` và `Integer.valueOf(7)` không có cùng kiểu.

## 4. Những chuỗi kết hợp được phép và bị chặn

Trong ngữ cảnh gọi phương thức, quy tắc `method invocation conversion` không cho phép nối tùy tiện mọi phép chuyển kiểu.

| Đối số | Tham số | Kết quả | Lý do |
| --- | --- | --- | --- |
| `byte` | `long` | Hợp lệ | Widening primitive |
| `int` | `Integer` | Hợp lệ | Boxing |
| `int` | `Object` | Hợp lệ | Boxing rồi widening reference: `int → Integer → Object` |
| `Integer` | `long` | Hợp lệ | Unboxing rồi widening primitive: `Integer → int → long` |
| `Integer` | `Number` | Hợp lệ | Widening reference |
| `int` | `Long` | **Không** | Không tự widening primitive rồi boxing: `int → long → Long` |
| `byte` | `Integer` | **Không** | Không tự widening primitive rồi boxing: `byte → int → Integer` |
| `Integer` | `Long` | **Không** | Không tự unbox, widen rồi box lại |
| `long` | `int` | **Không** | Narrowing primitive cần cast |

Hai mẫu kết hợp phải nhớ là **boxing + widening reference** và **unboxing + widening primitive**. Ngoài ra, quy tắc loose invocation trong JLS còn có trường hợp widening reference rồi unboxing (sau đó có thể widening primitive), nhưng không có nghĩa một `Object` bất kỳ tự động được unbox như kiểu mong muốn: quan hệ kiểu và wrapper phải hợp lệ.

Ví dụ sau cho thấy giới hạn rất cụ thể:

~~~java
static void acceptLong(Long number) { }

// acceptLong(7);          // LỖI: int không tự thành Long
acceptLong(7L);            // long -> Long: hợp lệ
acceptLong((long) 7);      // cast cho biểu thức có kiểu long, sau đó boxing
acceptLong(Long.valueOf(7L));
~~~

Với `acceptLong(7)`, compiler **không** tự thực hiện `int → long → Long`. Chọn literal `7L` hoặc chuyển biểu thức sang `long` trước khi gọi nếu API yêu cầu `Long`. Tương tự, một biến kiểu `Integer` không tự trở thành `Long`.

**Hằng số nguyên nhỏ không được tự narrowing khi gọi hàm.** `byte b = 7` là phép gán hợp lệ do quy tắc hằng số, nhưng `acceptByte(7)` không hợp lệ nếu hàm chỉ nhận `byte`, bởi literal `7` vẫn có kiểu `int`. Phải gọi `acceptByte((byte) 7)`.

## 5. Widening reference có thể được chọn trước unboxing

Xét hai overload:

~~~java
static String fromWrapper(Number value) {
    return "Number";
}
static String fromWrapper(long value) {
    return "long";
}
~~~

Với `Integer x = 7; fromWrapper(x)`, overload `Number` áp dụng bằng widening reference `Integer → Number` ở pha 1, trong khi overload `long` cần unboxing rồi widening `Integer → int → long` ở pha 2. Vì thế Java chọn `fromWrapper(Number)`.

Nếu lớp **chỉ có** `fromWrapper(long)`, lời gọi bằng `Integer` vẫn hoàn toàn hợp lệ vì `Integer → int → long` là một chuỗi cho phép ở pha loose invocation. Kết quả chọn `Number` phía trên xuất phát từ **thứ tự xét pha**, không phải vì mọi tham số object luôn được ưu tiên hơn primitive.

## 6. Ví dụ Java 17+ hoàn chỉnh

Lưu tệp dưới tên `OverloadConversions.java`:

~~~java
public class OverloadConversions {
    static String choose(long x) {
        return "long";
    }
    static String choose(Integer x) {
        return "Integer";
    }

    static String fromWrapper(Number x) {
        return "Number";
    }
    static String fromWrapper(long x) {
        return "long";
    }

    static String unboxAndWiden(long x) {
        return "long";
    }
    static String receiveObject(Object x) {
        return "Object";
    }

    static String dispatch(int x) {
        return "fixed int";
    }
    static String dispatch(int... xs) {
        return "varargs " + xs.length;
    }

    static String boxed(Integer x) {
        return "Integer";
    }

    public static void main(String[] args) {
        byte b = 7;
        System.out.println("choose(7)=" + choose(7));
        System.out.println("choose(b)=" + choose(b));
        System.out.println("choose(Integer.valueOf(7))="
                + choose(Integer.valueOf(7)));
        System.out.println("fromWrapper(Integer)="
                + fromWrapper(Integer.valueOf(7)));
        System.out.println("unboxAndWiden(Integer)="
                + unboxAndWiden(Integer.valueOf(7)));
        System.out.println("receiveObject(7)="
                + receiveObject(7));
        System.out.println("dispatch(7)=" + dispatch(7));
        System.out.println("dispatch(7, 8)=" + dispatch(7, 8));
        System.out.println("boxed(7)=" + boxed(7));
    }
}
~~~

Biên dịch và chạy với Java 17 trở lên:

~~~bash
javac OverloadConversions.java
java OverloadConversions
~~~

Stdout:

~~~text
choose(7)=long
choose(b)=long
choose(Integer.valueOf(7))=Integer
fromWrapper(Integer)=Number
unboxAndWiden(Integer)=long
receiveObject(7)=Object
dispatch(7)=fixed int
dispatch(7, 8)=varargs 2
boxed(7)=Integer
~~~

Trong chín dòng trên, `choose(7)` minh họa widening primitive được xét trước boxing; `fromWrapper(Integer)` minh họa widening reference trước unboxing; `unboxAndWiden(Integer)` và `receiveObject(7)` minh họa hai chuỗi hợp lệ; `dispatch(7)` ưu tiên overload cố định còn `dispatch(7, 8)` cần varargs; `boxed(7)` chứng minh boxing hợp lệ khi pha 1 không có phương thức phù hợp. Các kết quả có thể tái hiện bằng mã trên.

## 7. Hai ví dụ cố ý gây lỗi compile

Các đoạn sau là **mã minh họa lỗi**, không đưa nguyên vào chương trình chạy độc lập ở mục 6.

### Không có chuỗi widening rồi boxing

~~~java
static void accept(Long value) { }

accept(7); // ERROR: int không tự đổi thành Long
~~~

Sửa thành `accept(7L)` hoặc `accept(Long.valueOf(7L))` nếu định nghĩa hàm thực sự đòi wrapper `Long`. Không nên thêm overload chỉ để “dỗ” compiler nếu ngữ nghĩa API chưa rõ.

### Hai wrapper khác nhau gây mơ hồ với `null`

~~~java
static void process(Integer value) { }
static void process(Long value) { }

process(null); // ERROR: ambiguous method call
~~~

Cả hai overload đều nhận tham chiếu `null`, nhưng `Integer` và `Long` không phải subtype của nhau, nên không thể chọn một overload cụ thể hơn duy nhất. Có thể làm rõ ý định bằng `process((Integer) null)` hoặc `process((Long) null)`. Đoạn ví dụ này giả định các phương thức cùng nằm trong một lớp và được gọi ở nơi có thể truy cập.

## 8. Các lỗi suy luận và lưu ý thiết kế API

1. **Nhầm kiểu của literal với miền giá trị.** `7` là `int`; `7L` là `long`; gán được `7` vào `byte` không chứng minh gọi `f(byte)` bằng `f(7)` là hợp lệ.
2. **Nhầm wrapper với primitive cùng ý nghĩa số học.** `Integer` là tham chiếu, không phải alias của `int`. Compiler chỉ unbox ở những ngữ cảnh cho phép. Unboxing một wrapper `null` gây `NullPointerException`.
3. **Chọn overload theo kiểu runtime của object.** Nếu `Number n = Integer.valueOf(7)`, overload resolution nhìn thấy `Number`. Runtime polymorphism chọn implementation của **chữ ký đã chọn**, không quay lại chọn overload `Integer` chỉ vì object thật là `Integer`.
4. **Cho rằng varargs luôn ưu tiên hoặc luôn xếp sau mọi tình huống.** Phân biệt khai báo varargs được sử dụng như tham số mảng ở pha 1 với việc trải nhiều đối số riêng lẻ ở pha 3. Hai khai báo `f(int[])` và `f(int...)` không thể tồn tại như hai overload phân biệt, vì cùng chữ ký phương thức.
5. **Cho rằng kiểu trả về quyết định overload.** Không thể khai báo đồng thời `int f(int)` và `long f(int)` chỉ khác return type. Việc viết `long result = f(7)` không làm compiler “tìm chữ ký trả về long” như một tiêu chí đơn giản để chọn overload.
6. **Chọn theo số bước chuyển đổi.** Quy tắc đúng là phân pha rồi tìm phương thức cụ thể nhất trong pha phù hợp đầu tiên. Một chuỗi hai bước hợp lệ có thể được dùng nếu không có overload ở pha sớm hơn.
7. **Dùng cast để che mâu thuẫn API.** Cast `(long) 7` tạo biểu thức kiểu `long`; cast `(Integer) 7` tạo biểu thức kiểu `Integer`. Cast có thể giúp chủ động chọn overload nhưng làm thay đổi ngữ nghĩa nếu áp dụng tùy tiện.
8. **Mở rộng kết luận sang mọi generic/lambda.** Generic method inference, lambda và method reference có thêm quy tắc chọn overload cụ thể. Sử dụng ba pha như nền tảng, sau đó kiểm tra các quy tắc JLS liên quan và thử compiler với ví dụ thực tế.

## 9. Quy trình tự kiểm tra một lời gọi overload

1. Ghi chính xác **kiểu tĩnh** của từng đối số (`7`, `7L`, wrapper, biến tham chiếu, `null`).
2. Liệt kê các overload cùng tên có thể truy cập và phù hợp về số lượng tham số.
3. Tìm ứng viên **pha 1** chỉ bằng khớp kiểu/widening, không boxing/unboxing.
4. Nếu pha 1 rỗng, xét **pha 2** với boxing/unboxing và các chuỗi hợp lệ; không tự chèn primitive widening rồi boxing.
5. Nếu pha 2 rỗng, mới xét **pha 3** cho variable arity.
6. Trong pha đầu có ứng viên, chọn phương thức **cụ thể nhất**; nếu nhiều ứng viên không có lựa chọn duy nhất thì lỗi biên dịch. Sau đó mới nghĩ về giá trị runtime và unboxing `null`.

**Tự luyện:** Có `m(long)` và `m(Integer)`. `m(1)` chọn gì? `m(Integer.valueOf(1))` chọn gì? Một phương thức chỉ có chữ ký `use(Long)` có gọi được bằng `use(1)` không?

**Đáp án:** `m(1)` chọn `m(long)` (pha 1); `m(Integer.valueOf(1))` chọn `m(Integer)` (pha 1, khớp chính xác); `use(1)` không biên dịch vì `int → long → Long` không phải chuỗi chuyển đổi ngầm hợp lệ trong lời gọi.

## Tài liệu chuẩn

- [Java Language Specification §5.3 — Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3): các loại chuyển kiểu và chuỗi được phép.
- [Java Language Specification §15.12.2 — Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2): thứ tự ba pha và chọn phương thức cụ thể nhất.
