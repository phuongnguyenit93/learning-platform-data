# Kiểu nguyên thủy và kiểu tham chiếu trong mô hình thực thi JVM

Trong Java, một biến có thể mang **giá trị nguyên thủy (primitive value)** hoặc **giá trị tham chiếu (reference value)**. JVM cần biết loại giá trị để chọn lệnh bytecode, biểu diễn dữ liệu trong local variables và operand stack, kiểm tra tính đúng đắn của các thao tác và quản lý đối tượng. Phân biệt này giải thích tại sao gán một biến `int` lại sao chép con số, còn gán một biến chứa tham chiếu tới đối tượng có thể khiến hai biến cùng quan sát thay đổi trên đối tượng đó.

Nội dung tập trung vào **mô hình thực thi**, vì vậy cần tách ba khái niệm thường bị nhầm:

1. **Kiểu của ngôn ngữ Java**: trình biên dịch kiểm tra khai báo `int`, `boolean`, `String`, `int[]`, class, interface, generic...
2. **Kiểu và lệnh của JVM**: class file dùng type descriptor, tập lệnh như `iload`/`aload`, operand stack, local-variable slots và bytecode verifier để thực thi.
3. **Đối tượng trong bộ nhớ**: một tham chiếu dùng để truy cập đối tượng/mảng; GC và runtime quản lý vòng đời bộ nhớ theo triển khai JVM. Không thể suy ra bố cục bit hay vị trí vật lý từ riêng một khai báo Java.

## 1. Hai họ kiểu ở cấp ngôn ngữ Java

| Nhóm | Kiểu/giá trị tiêu biểu | Đặc tính khi gán |
| --- | --- | --- |
| **Primitive** | `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double` | Gán sao chép **giá trị** kiểu nguyên thủy |
| **Reference** | Biến của class (`String`, `Object`), interface, array (`int[]`), type variable và các kiểu tham chiếu khác | Gán sao chép **giá trị tham chiếu**, có thể cùng trỏ tới một đối tượng/mảng |
| **`null`** | Giá trị đặc biệt có thể dùng với các kiểu tham chiếu tương thích | Biểu thị **không tham chiếu đối tượng nào**; không gán được trực tiếp cho biến primitive |

Tám primitive trên là **kiểu của Java**, không phải tám loại lệnh độc lập trong JVM. `String` là class và `String` variable là tham chiếu, dù cú pháp literal `"hello"` trông đơn giản. Mảng nguyên thủy `int[]` **vẫn là đối tượng mảng**, vì vậy biến `int[]` là biến tham chiếu; **phần tử** của nó mới có kiểu `int`.

**Các trường hợp dễ nhầm:**

- `int number = 10;`: `number` chứa giá trị số nguyên; gán `int copy = number;` cho bản sao độc lập của giá trị.
- `Person p = new Person();`: `p` chứa giá trị tham chiếu tới một đối tượng, không phải toàn bộ đối tượng đặt “bên trong biến”.
- `Person q = p;`: sao chép **tham chiếu**; `p` và `q` có thể chỉ cùng một đối tượng. Đây **vẫn là truyền/gán theo giá trị (pass/copy by value)**, không phải “biến Java được truyền bằng tham chiếu”.
- `Person absent = null;`: biến có kiểu tham chiếu nhưng hiện không trỏ tới một đối tượng nào.
- `int[] data = {1, 2};`: `data` là tham chiếu, còn hai phần tử là các giá trị `int` được lưu trong đối tượng mảng.

## 2. Các primitive: ý nghĩa và phạm vi giá trị

| Kiểu Java | Ý nghĩa và kích thước giá trị theo đặc tả | Ghi chú |
| --- | --- | --- |
| `boolean` | Hai giá trị `false` và `true` | Java không cho chuyển trực tiếp qua lại với `int`; không mặc định “true là số 1” trong chương trình nguồn |
| `byte` | Số nguyên có dấu, 8 bit (`-128` đến `127`) | Phép toán số học thường được **promote lên `int`** |
| `short` | Số nguyên có dấu, 16 bit (`-32768` đến `32767`) | Phép toán `short + short` trả về `int` |
| `char` | Mã đơn vị **UTF-16**, không dấu, 16 bit (`0` đến `65535`) | Một `char` không nhất thiết biểu thị toàn bộ một ký tự Unicode ngoài BMP |
| `int` | Số nguyên có dấu, 32 bit | Tràn số nguyên được xử lý theo quy tắc Java, không tự biến thành kiểu rộng hơn |
| `long` | Số nguyên có dấu, 64 bit | Literal thường viết hậu tố `L` như `12L` |
| `float` | Số thực IEEE 754 binary32 | Có sai số làm tròn, giá trị đặc biệt NaN và vô cực |
| `double` | Số thực IEEE 754 binary64 | Có sai số làm tròn; mặc định của literal dấu phẩy động như `1.5` |

Các kích thước này mô tả **độ rộng và miền giá trị theo ngôn ngữ**, không có nghĩa mỗi biến luôn chiếm đúng từng ấy byte ở mọi nơi trong bộ nhớ máy. Cách JVM sắp xếp đối tượng, căn lề field, tối ưu biến hoặc bố trí CPU register phụ thuộc bản triển khai.

Ví dụ phép toán trên kiểu hẹp:

```java
byte a = 3;
byte b = 4;
int sum = a + b; // Kết quả biểu thức a + b có kiểu int
```

Dòng `byte sum = a + b;` không hợp lệ nếu thiếu ép kiểu vì phép cộng được **binary numeric promotion** thành `int`. Ngược lại, `byte x = 3 + 4;` có thể được `javac` chấp nhận nhờ quy tắc gán **hằng số nguyên biên dịch được** nằm trong phạm vi `byte`. Hai tình huống là hai quy tắc ngôn ngữ khác nhau.

## 3. JVM biểu diễn kiểu nào khi thực thi bytecode?

Trong JVM Specification, các giá trị JVM thường được phân thành nhóm số (numeric) và nhóm tham chiếu (reference). Numeric gồm `byte`, `short`, `int`, `long`, `char`, `float`, `double`; `boolean` không có một tập lệnh tính toán độc lập như `int`. JVM hỗ trợ `boolean` ở mức hạn chế, thường dùng biểu diễn và hướng dẫn liên quan `int` khi mã Java `boolean` được biên dịch.

Hai loại **category** rất quan trọng khi xem bytecode:

| JVM value | Category trên operand stack | Số local-variable slots |
| --- | ---: | ---: |
| `int`, `float`, `reference` và các giá trị narrow integral khi thao tác ở dạng `int` | 1 | 1 |
| `long`, `double` | 2 | 2 |
| `returnAddress` của cơ chế `jsr`/`ret` lịch sử | 1 | 1 |

**Category 1/2 là quy ước kích thước trong mô hình JVM**, không đồng nghĩa mọi reference vật lý đều có độ rộng bằng `int`. Những triển khai như HotSpot có thể có biểu diễn reference và tối ưu bộ nhớ khác nhau; địa chỉ máy và kỹ thuật compressed references là chi tiết triển khai.

Ở mức bytecode, `byte`, `short`, `char` thường được đẩy lên operand stack và xử lý như **`int`**. Chẳng hạn cộng hai `byte` có thể dùng `iadd` sau khi đã lấy các giá trị lên stack; khi cần ghi lại vào kiểu hẹp, compiler có thể dùng phép chuyển đổi như `i2b`, `i2s` hoặc `i2c`. Các lệnh tải/lưu array vẫn phân biệt element type phù hợp, ví dụ `baload`, `saload`, `caload`.

**Về `boolean`:** mã Java điều kiện thường dùng `iconst_0`/`iconst_1` cùng lệnh rẽ nhánh kiểu `if*`; JVM định nghĩa cách hỗ trợ `boolean` và mảng `boolean[]` chứ không bảo đảm một bytecode số học `boolean` riêng. Không được từ đó suy ra Java cho phép `if (1)` hoặc phép cộng giữa các `boolean`: **trình biên dịch Java bác bỏ các biểu thức đó**.

**`returnAddress`** là loại giá trị đặc biệt gắn với lệnh `jsr`/`ret` của class file cũ, không phải một kiểu mà mã Java thông thường có thể khai báo, và không nên dùng trong code Java hiện đại. `void` là kiểu kết quả “không có giá trị trả về”, không phải một giá trị được đặt vào operand stack.

## 4. Local variables, operand stack và đối tượng khác nhau thế nào?

Một phương thức Java khi chạy trong JVM có **stack frame** của riêng lượt gọi. Frame chứa:

- **Local variable array**: các slot được truy cập theo chỉ số cho tham số và biến cục bộ; giá trị category 2 chiếm hai slot liên tiếp trong mô hình.
- **Operand stack**: nơi bytecode đẩy, lấy và phối hợp các giá trị trung gian khi thực hiện phép tính, gọi phương thức, nhảy điều kiện.
- **Thông tin phụ trợ** cho việc trả về/kiểm soát luồng gọi và tham chiếu runtime liên quan.

Ví dụ khái niệm cho phương thức tĩnh:

```java
static int add(int left, int right) {
    return left + right;
}
```

Bytecode do `javac` thường biểu diễn phép cộng bằng các lệnh tương đương:

```text
iload_0     // đẩy giá trị int từ local slot 0
iload_1     // đẩy giá trị int từ local slot 1
iadd        // lấy hai int trên operand stack, đẩy kết quả int
ireturn     // lấy giá trị int trên stack để trả về
```

Đây là đoạn **minh họa bytecode**, không phải chương trình độc lập cần biên dịch; thứ tự và lựa chọn opcode cụ thể nên được kiểm tra bằng `javap -c` trên class file thực tế.

Với phương thức instance, local slot `0` thường chứa tham chiếu `this`; tham số xuất hiện ở các slot kế tiếp. Với phương thức `static`, không có `this` tự động. Một tham số `long` hoặc `double` dùng **hai slot**, nên chỉ số của tham số tiếp theo có thể nhảy qua một vị trí.

**Đừng hiểu “primitive luôn ở stack, object luôn ở heap” thành quy tắc tuyệt đối.** Biến cục bộ có thể chứa giá trị primitive hoặc reference; field bên trong object có thể có kiểu primitive hoặc reference; mảng có thể chứa primitive elements hay references. Trên bình diện mô hình JVM, đối tượng và mảng là thực thể heap; nhưng JVM tối ưu hiện đại có thể loại bỏ allocation hoặc biểu diễn dữ liệu khác đi khi giữ nguyên hành vi quan sát được.

```text
Stack frame của main() (mô hình logic)       Heap (mô hình logic)
┌───────────────────────────────┐           ┌──────────────────────┐
│ int count = 7                 │           │ Item instance        │
│ Item first ───────────────────┼──────────►│ int value = 9        │
│ Item alias ───────────────────┼──────────►│ boolean active=false │
│                               │           │ String label=null    │
└───────────────────────────────┘           └──────────────────────┘

first và alias giữ hai BẢN SAO giá trị tham chiếu,
nhưng đều truy cập CÙNG một đối tượng Item.
```

Sơ đồ chỉ giải thích quan hệ quan sát được, không phải lời khẳng định JVM luôn đặt từng biến vào một ô RAM vật lý riêng hay reference có hình dạng con trỏ máy cố định.

## 5. Ví dụ Java 17+ chạy được: sao chép giá trị và chia sẻ đối tượng

Tạo tệp **`JvmValueKinds.java`** trong một thư mục trống:

```java
public class JvmValueKinds {
    static class Item {
        int value;
        boolean active;
        String label;
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        int original = 7;
        int copied = original;
        copied = 10;

        Item first = new Item();
        first.value = 7;
        Item alias = first;

        Item another = new Item();
        another.value = 7;
        alias.value = 10;

        Item fresh = new Item();

        byte left = 3;
        byte right = 4;
        int promotedSum = add(left, right);

        int[] numbers = {1, 2};
        int[] shared = numbers;
        shared[0] = 99;

        Integer boxed = 42;
        int unboxed = boxed;

        System.out.println("primitive: original=" + original
                + ", copied=" + copied);
        System.out.println("reference: first.value=" + first.value);
        System.out.println("same object: " + (first == alias));
        System.out.println("different objects: " + (first == another));
        System.out.println("defaults: " + fresh.value
                + ", " + fresh.active + ", " + fresh.label);
        System.out.println("byte + byte -> int: " + promotedSum);
        System.out.println("array alias: " + numbers[0]);
        System.out.println("boxed/unboxed: " + unboxed);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 JvmValueKinds.java
java JvmValueKinds
```

**Standard output chính xác:**

```text
primitive: original=7, copied=10
reference: first.value=10
same object: true
different objects: false
defaults: 0, false, null
byte + byte -> int: 7
array alias: 99
boxed/unboxed: 42
```

Giải thích từng quan sát:

1. **Primitive:** `copied = original` tạo bản sao giá trị `7`. Đặt `copied = 10` không làm `original` thay đổi.
2. **Reference:** `alias = first` sao chép giá trị tham chiếu tới cùng `Item`. `alias.value = 10` sửa **trường của đối tượng**, nên `first.value` cũng đọc ra `10`.
3. **Identity:** `first == alias` là `true` vì hai reference chỉ cùng một object; `first == another` là `false` vì hai lần `new Item()` tạo hai đối tượng riêng, dù field `value` từng có cùng giá trị `7`.
4. **Giá trị mặc định:** instance fields `int`, `boolean`, `String` chưa gán tường minh lần lượt có `0`, `false`, `null`. Quy tắc này **không áp dụng cho local variables** chưa được gán trước khi đọc: trình biên dịch buộc local variables phải được khởi tạo chắc chắn.
5. **Numeric promotion:** `left` và `right` là `byte`; chúng được chuyển đổi theo lời gọi `add(int, int)`, kết quả `int` là `7`. Phép cộng trong `add` là phép cộng `int`.
6. **Array reference:** `shared = numbers` sao chép tham chiếu, nên sửa `shared[0]` thay đổi phần tử quan sát từ `numbers[0]`.
7. **Boxing:** `Integer boxed = 42` thực hiện autoboxing; `int unboxed = boxed` thực hiện unboxing. `Integer` là object reference type; `int` là primitive. Compiler có thể dùng các lời gọi như `Integer.valueOf` và `Integer.intValue`.

Lưu ý trong ví dụ, phép gán `alias = first` **không tạo ra một `Item` mới**; chỉ `new Item()` yêu cầu tạo đối tượng theo ngữ nghĩa chương trình.

### Tự nhìn vào bytecode

```bash
javap -c JvmValueKinds
javap -c -p JvmValueKinds
javap -verbose JvmValueKinds
```

- `javap -c` in bytecode của các phương thức công khai thông thường; `-p` cho phép xem thêm thành phần không public.
- Trong `add(int, int)`, quan sát `iload`, `iadd`, `ireturn`. Đó là các lệnh **`int`**, dù đầu vào `left` và `right` ở `main` có kiểu `byte`.
- Với `new Item()`, compiler thường tạo nhóm `new`, `dup`, `invokespecial` để cấp phát đối tượng và gọi constructor. Việc truy cập `value` dùng `getfield`/`putfield`.
- Đối với `new int[]` hay array initializer, quan sát các lệnh liên quan mảng như `newarray`, `iastore`, `iaload`.
- Các lệnh cho phép in chuỗi có thể dùng `invokedynamic` để nối chuỗi trên JDK hiện đại; chi tiết chỉ số constant pool và offset phụ thuộc bản compiler.

**Không nhầm bytecode của `javap` với mã máy CPU.** Khi JVM thực thi, interpreter hoặc JIT xử lý bytecode phù hợp với nền tảng hiện tại.

## 6. Descriptor trong class file nói gì về kiểu?

JVM class file dùng **type descriptor** để ghi kiểu của field và chữ ký phương thức ở mức bytecode. Các ký hiệu primitive:

| Kiểu Java | Ký hiệu trong field descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `short` | `S` |
| `char` | `C` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |

Tham chiếu tới class thường có dạng **`Lten/package/Class;`**. Kiểu array có tiền tố **`[`**; nhiều dấu `[` biểu thị nhiều chiều. `V` nghĩa là `void` **trong phần kiểu trả về của method descriptor**, không phải field type.

| Khai báo Java | JVM descriptor |
| --- | --- |
| `int number` | `I` |
| `String text` | `Ljava/lang/String;` |
| `int[] values` | `[I` |
| `String[][] names` | `[[Ljava/lang/String;` |
| `static int add(int a, int b)` | `(II)I` |
| `void use(String[] args)` | `([Ljava/lang/String;)V` |

Method descriptor có cấu trúc **`(parameter-descriptors)return-descriptor`**. Dấu gạch chéo trong `java/lang/String` là tên nội bộ của class file, khác cách viết tên Java `java.lang.String`.

Generic như `List<String>` có thêm thông tin khai báo/metadata tương ứng khi compiler lưu, nhưng phần descriptor cơ bản hoạt động trên kiểu sau **erasure**; đừng mong bytecode luôn bảo toàn đầy đủ mọi tham số generic của ngôn ngữ nguồn. Kiểm tra `javap -verbose` để quan sát descriptor và, khi có, thuộc tính `Signature`.

## 7. Bytecode chọn instruction theo loại giá trị

Opcode của JVM thường có tiền tố gợi ý nhóm kiểu:

| Nhóm thao tác | Với `int` | Với `long` | Với `float`/`double` | Với reference |
| --- | --- | --- | --- | --- |
| Load local variable | `iload` | `lload` | `fload`/`dload` | `aload` |
| Store local variable | `istore` | `lstore` | `fstore`/`dstore` | `astore` |
| Return value | `ireturn` | `lreturn` | `freturn`/`dreturn` | `areturn` |
| Cộng số | `iadd` | `ladd` | `fadd`/`dadd` | Không có lệnh cộng hai reference |

Các phép cộng với `byte`, `short`, `char` thường được xử lý trong miền `int` theo numeric promotion. `boolean` cũng không được xem là số nguyên của ngôn ngữ Java để dùng `iadd` trong mã Java hợp lệ.

Một số lệnh đặc thù reference:

- `new`: tạo instance của class.
- `getfield`/`putfield`: đọc/ghi instance field; `getstatic`/`putstatic` phục vụ static field.
- `invokevirtual`, `invokeinterface`, `invokespecial`, `invokestatic`: các cơ chế gọi method; không đơn thuần là “nhảy tới một con trỏ”.
- `checkcast` và `instanceof`: kiểm tra quan hệ kiểu tham chiếu thích hợp ở runtime.
- `ifnull`/`ifnonnull`, `if_acmpeq`/`if_acmpne`: rẽ nhánh liên quan null hoặc so sánh identity reference.
- `aaload`/`aastore`: đọc/ghi phần tử mảng reference, trái với `iaload`/`iastore` cho `int[]`.

**Bytecode verifier** dùng loại giá trị và trạng thái của local variables/operand stack để bác bỏ những bytecode không thỏa mãn luật kiểu và cấu trúc. Ví dụ không thể hợp lệ nếu đẩy reference rồi dùng `iadd` như với `int`. Verifier còn theo dõi trạng thái đối tượng chưa khởi tạo và các ràng buộc luồng điều khiển; việc Java source biên dịch được không cho phép một công cụ bytecode tự do sinh mã sai kiểu.

## 8. Tham chiếu không phải chính đối tượng

Cần phân biệt ba thao tác dưới đây:

```java
Item a = new Item(); // tạo object mới, a giữ reference
Item b = a;          // sao chép reference: cùng object
b = new Item();      // b nhận reference mới, a vẫn tới object cũ
```

Hai biến `a` và `b` là hai **vị trí lưu giá trị tham chiếu** riêng theo mô hình biến. Khi chỉ gán `b = a`, đối tượng không được sao chép; khi gán lại `b = new Item()`, quan hệ alias bị thay đổi mà không tự sửa `a`.

Khi gọi phương thức:

```java
static void replace(Item parameter) {
    parameter = new Item();
}

static void mutate(Item parameter) {
    parameter.value = 99;
}
```

Cả hai đoạn trên là **hàm phụ trợ minh họa** và cần nằm trong class có khai báo `Item` tương thích mới biên dịch; chúng không tạo thành chương trình chạy độc lập.

- `replace(a)` chỉ thay **bản sao giá trị reference trong tham số `parameter`**, không chuyển `a` sang object mới.
- `mutate(a)` sửa **field của object mà tham số và `a` cùng tham chiếu**, nên caller có thể quan sát `a.value == 99`.

Do đó Java **luôn truyền đối số theo giá trị**: với primitive là bản sao giá trị primitive, với reference là bản sao giá trị reference. Cụm từ “Java truyền object theo tham chiếu” dễ làm người học kết luận sai rằng có thể gán lại biến tham chiếu của caller từ một parameter.

### `==`, `equals` và các wrapper

Với primitive số, `==` so sánh giá trị theo quy tắc numeric conversion của Java; với hai reference, `==` kiểm tra **cùng identity hoặc cùng null**. So sánh **nội dung mang ý nghĩa nghiệp vụ** của hai object cần một phương thức thích hợp như `equals` nếu class cung cấp hợp đồng so sánh đó.

Ví dụ:

```java
String left = new String("abc");
String right = new String("abc");
System.out.println(left == right);      // false (hai object mới)
System.out.println(left.equals(right)); // true  (nội dung bằng nhau)
```

Đây là **đoạn minh họa đặt trong `main`**, không phải một class hoàn chỉnh. Không dùng `==` để so sánh nội dung `String`: các string literal có thể được intern nên cho kết quả identity trùng trong vài tình huống, làm lỗi bị che giấu.

Autoboxing biến primitive thành giá trị wrapper reference như `Integer`; unboxing lấy giá trị primitive từ wrapper. Nếu biến wrapper là `null` thì **unboxing ném `NullPointerException`**. Không dựa vào `==` giữa hai wrapper để so giá trị vì **identity/caching** có thể tạo kết quả không như trực giác; dùng `equals` hoặc unbox an toàn khi muốn so nội dung.

## 9. Field, local variable, array: cùng kiểu nhưng quy tắc khởi tạo khác

| Vị trí | Giá trị trước gán tường minh | Ghi chú |
| --- | --- | --- |
| Instance field / static field | Có default value như `0`, `false`, `null` | Khởi tạo theo quy tắc JVM; constructor/static initialization có thể gán tiếp |
| Phần tử mảng mới | Có default value của element type | Ví dụ `new int[2]` chứa `0, 0`; `new String[2]` chứa `null, null` |
| Local variable trong phương thức Java | **Không thể đọc trước khi được gán chắc chắn** | Quy tắc **definite assignment** của `javac`; không coi là có default `0`/`null` |

Ví dụ:

```java
int[] numbers = new int[2];       // numbers tham chiếu mảng; phần tử là int
String[] names = new String[2];  // names tham chiếu mảng; phần tử là reference
System.out.println(numbers[0]); // 0
System.out.println(names[0]);   // null
```

Đoạn trên hợp lệ khi nằm trong một `main` hoặc phương thức thích hợp. Các biến `numbers` và `names` ở ví dụ đều được gán bởi `new` trước khi dùng.

Với mảng reference, JVM còn kiểm tra tính tương thích kiểu phần tử tại runtime (vì Java arrays có tính **covariant**):

```java
Object[] values = new String[1];
values[0] = "ok";            // hợp lệ
// values[0] = new Object(); // nếu bỏ comment: ArrayStoreException tại runtime
```

Type check của mảng khác với việc copy reference và khác với lỗi compilation. `int[]` không thể chuyển trực tiếp thành `Object[]`; dù cả hai đều là object array theo nghĩa Java object, `int[]` có phần tử primitive.

## 10. `null`, truy cập đối tượng và garbage collection

`null` là một **giá trị reference đặc biệt**, không có object tương ứng. Truy cập instance field hoặc gọi instance method qua reference `null` thường dẫn tới `NullPointerException` tại runtime:

```java
String text = null;
// System.out.println(text.length()); // nếu bỏ comment: NullPointerException
System.out.println(text == null); // true
```

`null` không phải `0` và không thể gán vào `int`. Lệnh `instanceof` khi toán hạng là `null` cho kết quả `false`, nhưng không có nghĩa mọi phép thao tác khác với `null` đều an toàn.

**Reachability** giúp GC xác định object còn có thể được chương trình dùng từ những nguồn tham chiếu mà collector xét. Khi không còn đường tham chiếu có liên quan tới object, object có thể **đủ điều kiện được thu gom**, nhưng **không có cam kết bị thu gom ngay lập tức**. Gán `reference = null` không tương đương việc “xóa object khỏi heap” ngay lúc đó, và không thể dựa vào `System.gc()` để bảo đảm thời điểm thu hồi.

Không tồn tại phép toán pointer arithmetic trên reference trong Java source như C/C++; đặc tả cũng không cho phép giả định biểu diễn reference có số byte cố định để cộng/trừ địa chỉ.

## 11. Các hiểu nhầm phổ biến khi học JVM types

| Nhận định dễ nhầm | Cách hiểu đúng |
| --- | --- |
| “Primitive luôn nằm ở stack; reference luôn ở heap.” | Biến/field/mảng có thể lưu primitive hoặc reference; **object** là thực thể heap trong mô hình, còn bố trí vật lý có thể được JVM tối ưu |
| “Gán object `b = a` là deep copy object.” | Gán sao chép **giá trị reference**; hai biến có thể dùng chung object |
| “Tham số class được truyền by reference.” | Java **pass by value** kể cả với tham chiếu tới object |
| “`long` chiếm hai slot nghĩa là reference cũng luôn là 4 byte.” | Category và slot là **mô hình JVM**, không suy ra kích thước pointer vật lý |
| “Có 8 primitive Java nên JVM phải có 8 opcode cộng khác nhau.” | JVM dùng `int` cho nhiều thao tác trên kiểu narrow; `boolean` không có phép cộng Java |
| “Array luôn là tham chiếu tới một mảng các object.” | Mảng là object; **element type** có thể là primitive (`int[]`) hoặc reference (`String[]`) |
| “Field và local variable chưa gán đều bằng `0`.” | Field/array element có default; local variable Java phải được gán chắc chắn trước khi đọc |
| “`Integer` giống hệt `int`.” | `Integer` là reference wrapper, có thể `null` và có identity; unboxing có thể lỗi |
| “`==` luôn so nội dung object.” | Với reference, `==` so identity; `equals` có thể so nội dung tùy hợp đồng class |

## 12. Tự kiểm tra mô hình thực thi

**Câu 1.** `int[] a = new int[3];` thì `a` thuộc primitive hay reference?  
**Trả lời:** `a` có kiểu **reference**, trỏ tới một đối tượng mảng. Mỗi phần tử `a[i]` mang giá trị primitive `int`.

**Câu 2.** Vì sao `byte a = 1, b = 2; byte c = a + b;` không biên dịch được?  
**Trả lời:** Phép cộng áp dụng numeric promotion tạo biểu thức có kiểu `int`, nên cần nơi nhận `int` hoặc chuyển đổi tường minh thích hợp; không tự gán biểu thức `int` không phải hằng số cho `byte`.

**Câu 3.** `long` và `double` chiếm mấy local slots trong frame?  
**Trả lời:** Mỗi giá trị chiếm **hai slots** theo mô hình JVM; điều này không xác định chính xác bố trí RAM cuối cùng.

**Câu 4.** Hai reference trỏ cùng object; đổi field qua reference A, reference B thấy gì?  
**Trả lời:** B có thể quan sát giá trị field mới của **cùng object**, theo các quy tắc về đồng bộ và memory visibility nếu có nhiều thread. Trong một luồng thực thi thông thường, thay đổi field quan sát được ngay qua alias đó.

**Câu 5.** Vì sao có thể `getfield` cho reference nhưng không được `iadd` hai reference?  
**Trả lời:** Bytecode verifier và mô hình kiểu phân biệt reference với numeric operands. `iadd` yêu cầu hai giá trị `int`, trong khi `getfield` thao tác trên object reference phù hợp với field được chỉ định.

**Câu 6.** Có thể xác định một biến tham chiếu luôn chiếm đúng 8 byte vì ứng dụng chạy trên JVM 64-bit?  
**Trả lời:** **Không.** Cách biểu diễn và tối ưu tham chiếu phụ thuộc JVM/cấu hình; descriptor và operand-stack category không mã hóa chiều rộng địa chỉ native cố định.

**Câu 7.** Vì sao `Integer number = null; int x = number;` thất bại dù compiler chấp nhận?  
**Trả lời:** `Integer` là kiểu tham chiếu có thể bằng `null`; phép **unboxing tại runtime** cố lấy giá trị `int` từ `null` nên ném `NullPointerException`.

Tóm lại, **giá trị primitive** được copy theo nội dung, còn **giá trị reference** được copy như một đầu mối truy cập object. JVM phản ánh phân biệt đó bằng **type descriptor, instruction family, local-variable slots, operand stack và bytecode verification**; việc thực sự bố trí bộ nhớ thuộc trách nhiệm runtime/JIT/GC. Hiểu các tầng này sẽ giúp đọc `javap`, chẩn đoán `NullPointerException`, tránh nhầm pass-by-value và giải thích chính xác hành vi của các phép gán, mảng, field và method call.