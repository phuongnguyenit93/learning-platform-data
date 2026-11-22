# 11.4 Phân biệt đối số truyền cho bootstrap với đối số của lời gọi thực tế

Trong Java, lệnh bytecode `invokedynamic` tách **việc liên kết điểm gọi** (*linkage*) khỏi **việc thực thi điểm gọi** (*invocation*). Vì vậy có hai nhóm đối số rất khác nhau:

1. **Đối số cho bootstrap method (BSM):** dùng để **quyết định điểm gọi này sẽ liên kết đến hành vi nào**. JVM cung cấp sẵn ngữ cảnh `MethodHandles.Lookup`, tên điểm gọi `String` và kiểu điểm gọi `MethodType`; ngoài ra có thể có các **bootstrap arguments được ghi trong class file** (hằng số, `MethodHandle`, `MethodType`...). Bootstrap chạy trong quá trình liên kết để cung cấp một `CallSite`.
2. **Đối số của lời gọi thực tế:** là **các giá trị trên operand stack** ở thời điểm lệnh `invokedynamic` được thực thi (sau khi liên kết); chúng được chuyển tới target của `CallSite` theo chữ ký mà điểm gọi đã khai báo. Dữ liệu này thay đổi giữa các lượt gọi theo luồng chương trình.

Nguyên tắc: **bootstrap arguments định cấu hình cách gọi; invocation arguments cung cấp dữ liệu của từng lần gọi.** Hai loại có thể cùng là `String` hoặc `int`, nhưng chúng đi qua **hai đường khác nhau, ở hai giai đoạn khác nhau**.

Bài học dùng JVM class file, `BootstrapMethods`, `MethodType`, `CallSite`, `StringConcatFactory` và `LambdaMetafactory` để chỉ ra sự khác biệt, kèm ba ví dụ Java 17+ (một mô phỏng minh bạch qua API và hai trường hợp `javac` thực sự sinh `invokedynamic`).

## 1. Nhìn tổng thể qua sơ đồ hai giai đoạn

~~~text
                         CLASS FILE
 ┌────────────────────────────────────────────────────┐
 │ CONSTANT_InvokeDynamic_info                        │
 │   - bootstrap_method_attr_index                    │
 │   - name_and_type_index                            │
 │                                                    │
 │ BootstrapMethods attribute                         │
 │   - bootstrap_method_ref                           │
 │   - bootstrap_arguments[] (các hằng số đã ghi sẵn) │
 └────────────────────────────────────────────────────┘
                        │
          Liên kết invokedynamic call site
                        │
                        ▼
       JVM gọi bootstrap với thông tin:
       (Lookup, invokedName, invokedType, staticArg1, ...)
                        │
                        ▼
             BSM tạo/trả về CallSite
                        │
                        ▼
               CallSite.target
                        ▲
                        │
       Thực thi invokedynamic theo descriptor
       (runtimeArg1, runtimeArg2, ...) -> result
                        ▲
                        │
            Giá trị từ operand stack
~~~

**Không phải** mỗi lần chạy `invokedynamic` đều phải gọi bootstrap rồi mới gọi target. Liên kết thường diễn ra khi điểm gọi được cần đến lần đầu; sau khi thành công, các lần thực thi dùng target của call site đã liên kết. Ở môi trường có nhiều luồng cùng kích hoạt linkage, JVM có thể thực hiện nhiều hoạt động bootstrap cạnh tranh rồi chọn một kết quả; vì vậy **không được thiết kế dựa trên giả định BSM nhất định chỉ chạy đúng một lần trên toàn bộ mọi lịch thực thi**.

Tên `invokedName` và `invokedType` là thông tin JVM lấy từ chính điểm gọi; chúng khác với các *bootstrap arguments bổ sung* nằm trong `BootstrapMethods`. Mỗi điểm gọi trong bytecode có liên kết và chữ ký của nó, kể cả khi nhiều điểm gọi cùng dùng một bootstrap method.

## 2. Nhận diện chính xác ba nhóm dữ liệu

Thay vì gọi chung mọi thứ là “tham số của invokedynamic”, hãy đặt tên:

| Nhóm | Nơi xuất phát | Khi nào được dùng? | Ví dụ | Vai trò |
| --- | --- | --- | --- | --- |
| **Thông tin chuẩn do JVM truyền cho BSM** | Tên, descriptor của điểm gọi và ngữ cảnh JVM | Trong linkage | `Lookup lookup`, `String name`, `MethodType type` | Cho BSM biết điểm gọi đang được liên kết |
| **Bootstrap static arguments bổ sung** | `BootstrapMethods.bootstrap_arguments[]` trong class file | Trong linkage | recipe `"user=\u0001"`, một `MethodHandle`, một `MethodType`, số `42` | Cấu hình cách chọn/xây target |
| **Runtime invocation arguments** | Operand stack của luồng thực thi | Mỗi lần lệnh `invokedynamic` thực thi | `user="Lan"`, `score=81` | Dữ liệu mà target nhận và xử lý |

Các trường hợp không nên nhầm:

- **Bootstrap static argument không đồng nghĩa biến `static` của Java.** Chữ “static” ở đây nói về đối số **cố định trong mô tả bootstrap của class file**, không phải modifier `static` trên field hoặc method.
- **Không phải mọi đối số được đưa vào bootstrap đều ghi ở `bootstrap_arguments[]`.** Ba tham số đầu `Lookup`, `String name` và `MethodType` do JVM cung cấp; chúng là **thông tin chuẩn**, không phải ba phần tử do người lập trình thêm vào array của class file.
- **Một đối số runtime có thể luôn giữ cùng giá trị.** Nó vẫn là runtime argument vì được nạp lên operand stack khi lời gọi chạy, không phải vì giá trị chắc chắn thay đổi. Ngược lại, static argument có thể ảnh hưởng tới hành vi tạo ra target nhận dữ liệu thay đổi.
- **Return type của `invokedynamic` không phải đối số runtime**. Nó nằm trong descriptor của điểm gọi, được biểu diễn trong `MethodType` mà bootstrap nhận, và quyết định số/kiểu giá trị trả về trên stack.
- **Không có implicit receiver cho `invokedynamic` theo kiểu `invokevirtual`.** Nếu một receiver cần thiết, nó phải xuất hiện như một tham số rõ ràng trong descriptor và được đưa lên stack tương ứng.

## 3. JVM biết BSM và đối số tĩnh ở đâu?

Class file chứa một `CONSTANT_InvokeDynamic_info` trong constant pool, về logic gắn:

- **`bootstrap_method_attr_index`**: chỉ tới một entry trong bảng `BootstrapMethods` của class.
- **`name_and_type_index`**: cho biết tên call site và **method descriptor** của `invokedynamic`, ví dụ `(Ljava/lang/String;I)Ljava/lang/String;` nghĩa là nhận `String, int` và trả `String`.

Bảng `BootstrapMethods` chứa `bootstrap_method_ref` (tham chiếu `MethodHandle` tới BSM) và danh sách `bootstrap_arguments[]`. Các phần tử này là những hằng số có thể nạp được theo quy tắc của class file: chẳng hạn `String`, số primitive được biểu diễn bằng constant pool, `Class`, `MethodType`, `MethodHandle`, và trong class file hiện đại có thể dùng dynamic constants khi hợp lệ.

Điều này mang lại một khác biệt quan trọng:

~~~text
CONSTANT_InvokeDynamic
  name = makeConcatWithConstants
  descriptor = (Ljava/lang/String;I)Ljava/lang/String;
  bootstrap method = StringConcatFactory.makeConcatWithConstants
  static arguments = recipe "user=\u0001; score=\u0001"

Khi chạy lần 1:
  operand stack cung cấp ("Lan", 81)
  target tạo "user=Lan; score=81"

Khi chạy lần 2:
  operand stack cung cấp ("Minh", 40)
  target tạo "user=Minh; score=40"
~~~

`recipe` được chọn ở bước linkage, còn `"Lan"`, `81`, `"Minh"`, `40` là các đối số thực tế ở bước invocation. Recipe không tự được đưa vào danh sách đầu vào `(String,int)String` của lời gọi, trừ khi BSM cố ý xây target có cơ chế sử dụng recipe đó bên trong.

**Phân biệt hai descriptor:** descriptor của **bootstrap method** (nhận `Lookup`, `String`, `MethodType`, các cấu hình bổ sung...) không phải descriptor của **invokedynamic call site** (chỉ các đối số runtime và return type). Chữ ký của method gốc mà BSM chọn cũng có thể khác cả hai, bởi BSM được phép gắn sẵn tham số hoặc tạo adapter.

## 4. Bootstrap method được gọi với những gì?

Một BSM thường có hình dạng Java tương đương:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup lookup,
        String invokedName,
        MethodType invokedType,
        String recipe,
        int mode) throws Throwable {
    // Dựa vào thông tin linkage và cấu hình để tạo CallSite.
    // Không phải code triển khai hoàn chỉnh.
    throw new UnsupportedOperationException();
}
~~~

Đây là **minh họa chữ ký**, không phải BSM thực thi được: method cố ý ném exception và thiếu ngữ cảnh lớp bao. BSM có thể dùng kiểu phù hợp hoặc varargs cho các bootstrap argument bổ sung theo hợp đồng JVM; chữ ký cụ thể phụ thuộc loại BSM. Với `invokedynamic`, kết quả linkage hợp lệ là `CallSite` có target với chữ ký tương ứng điểm gọi.

Các thông số:

**`lookup` — bối cảnh tìm kiếm và quyền truy cập.** JVM cung cấp lookup cho lớp chứa lệnh đang liên kết. BSM dùng nó để `findStatic`/`findVirtual`/... hoặc tạo handle phù hợp quyền truy cập. Không nhầm với receiver runtime.

**`invokedName` — tên được ghi trong `NameAndType`.** Ví dụ tên bootstrap được yêu cầu là `makeConcatWithConstants` trong một call site do compiler sinh. Tên này giúp BSM phân biệt điểm gọi khi cần, nhưng nó **không tự là một argument nghiệp vụ** của target.

**`invokedType` — chữ ký thực thi của `invokedynamic`.** Ví dụ `(String,int)String`. Nó cho biết các giá trị sẽ được lấy từ stack khi gọi và kiểu kết quả sẽ được đẩy trở lại. BSM phải trả về `CallSite` có `type()` phù hợp chính xác chữ ký này.

**`recipe`, `mode` — static bootstrap arguments bổ sung.** Chúng được ghi vào `BootstrapMethods` (hoặc trong ví dụ mô phỏng là truyền khi chủ động gọi hàm Java). Chúng giúp BSM quyết định target, không tự động trở thành tham số của target. BSM có thể dùng `insertArguments`, `bindTo`, `asType`, `guardWithTest` và các combinator để đưa cấu hình vào hành vi cần gọi.

### Điều gì xảy ra nếu BSM sai?

Nếu bootstrap không thể thực hiện linkage, ném lỗi, trả kết quả không hợp lệ hoặc `CallSite` có chữ ký không khớp, JVM có thể báo `BootstrapMethodError` tại bước liên kết. Đây **khác** `WrongMethodTypeException` khi code sau đó dùng sai `invokeExact` trên một handle. Không nên catch mọi lỗi linkage rồi giả vờ đó là lỗi input người dùng.

BSM nên tạo target có type được kiểm tra kỹ trước khi trả về, đặc biệt khi dùng nhiều combinator làm thay đổi danh sách tham số.

## 5. Đối số runtime của invokedynamic là gì?

Một lệnh bytecode `invokedynamic` được gắn với một method descriptor, ví dụ:

~~~text
(String,int)String
~~~

Để thực thi một lời gọi theo descriptor này, JVM lấy từ operand stack một tham chiếu `String` và một số nguyên `int` theo đúng thứ tự, rồi thực thi target hiện tại của call site với các giá trị đó. Nếu method descriptor có kiểu trả về khác `void`, kết quả được đặt lại lên stack.

Cách nhìn giản lược từ bytecode:

~~~text
aload_0          // nạp String user (runtime)
iload_1          // nạp int score (runtime)
invokedynamic ... (Ljava/lang/String;I)Ljava/lang/String;
areturn          // trả String đã xử lý
~~~

Đoạn trên là **mô hình bytecode**, không phải toàn bộ file `javap` literal với số constant-pool cụ thể. Giá trị của `user` và `score` được nạp bởi code chạy trước opcode, không được đọc từ `bootstrap_arguments[]`.

Các điểm then chốt:

- **Kiểu của invocation arguments** đến từ descriptor, không đến từ kiểu tình cờ của các biến trong BSM.
- **Giá trị runtime** có thể đến từ biến local, field, kết quả phương thức khác, hoặc hằng được đẩy lên stack tại runtime. Dù giá trị ban đầu là literal `"Lan"` trong source, nó vẫn là runtime argument của chính opcode khi được đặt lên stack để gọi.
- `invokedynamic` không bắt buộc có runtime argument. Với descriptor `()String`, lời gọi không tiêu thụ đối số; BSM vẫn có thể nhận nhiều bootstrap arguments cấu hình.
- Không mặc định mọi BSM có side effect chỉ chạy khi mỗi invocation chạy; hai giai đoạn này được tách biệt.

## 6. MethodType là cầu nối, nhưng không phải danh sách giá trị

Hai đại lượng cần phân biệt:

~~~java
MethodType siteType =
        MethodType.methodType(
                String.class, String.class, int.class);
// siteType.toString() = "(String,int)String"
~~~

`siteType` chỉ mô tả **một `String` và một `int` được truyền lúc gọi**. Nó không chứa giá trị `"Lan"` hay `81`. BSM nhận `siteType` tại lúc linkage để biết target phải có kiểu gì.

Tương tự:

~~~java
MethodHandle target = /* handle hợp lệ */;
MethodType actual = target.type();
~~~

`actual` mô tả input/output của handle, không phải dữ liệu của một lượt thực thi. Nếu BSM tạo raw handle `(String,int,String,int)String` nhưng call site cần `(String,int)String`, nó phải xây thêm adapter, ví dụ gắn `prefix` và `minScore` vào hai tham số đầu. Sau đó:

~~~text
raw target:
  (String prefix, int minScore, String user, int score)String

sau khi insertArguments(raw, 0, prefix, minScore):
  (String user, int score)String

call site cần:
  (String user, int score)String   ✓
~~~

Đây là **một cách sử dụng cấu hình static**: giá trị cấu hình không xuất hiện ở chữ ký lời gọi cuối, nhưng đã được lưu trong handle. Một BSM khác có thể dùng static argument để **chọn** giữa nhiều target thay vì bind; JVM không ép mọi BSM phải dùng `insertArguments`.

## 7. Ví dụ Java 17+ hoàn chỉnh 1: mô phỏng linkage bằng API

Chương trình dưới đây **không tự sinh một opcode `invokedynamic` cho cuộc gọi được mô phỏng**. Nó gọi hàm `bootstrap(...)` trực tiếp trong Java để bạn quan sát rành mạch sự khác biệt, sau đó gọi `CallSite.dynamicInvoker()` hai lần. Mục đích là nhìn thấy bốn giá trị cấu hình và runtime được sử dụng ở giai đoạn nào; ví dụ thật do `javac` sinh `invokedynamic` sẽ xuất hiện ở phần tiếp theo.

Tạo file **BootstrapArgumentsDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class BootstrapArgumentsDemo {
    private static int bootstrapCalls;

    public static String render(
            String prefix, int minimum, String user, int score) {
        String result = score >= minimum ? " PASS" : " RETRY";
        return prefix + user + "=" + score + result;
    }

    public static CallSite bootstrap(
            MethodHandles.Lookup lookup,
            String invokedName,
            MethodType invokedType,
            String prefix,
            int minimum) throws ReflectiveOperationException {

        bootstrapCalls++;
        System.out.println("bootstrap name: " + invokedName);
        System.out.println("bootstrap type: " + invokedType);
        System.out.println("static arguments: " + prefix + " | " + minimum);

        MethodType rawType = MethodType.methodType(
                String.class,
                String.class, int.class, String.class, int.class);
        MethodHandle raw = lookup.findStatic(
                BootstrapArgumentsDemo.class, "render", rawType);

        // Hai giá trị cấu hình được gắn vào target.
        // raw: (String,int,String,int)String
        // bound: (String,int)String
        MethodHandle bound = MethodHandles.insertArguments(
                raw, 0, prefix, minimum);

        if (!bound.type().equals(invokedType)) {
            throw new IllegalArgumentException(
                    "wrong call-site type: " + bound.type());
        }

        return new ConstantCallSite(bound);
    }

    public static void main(String[] args) throws Throwable {
        MethodType runtimeType = MethodType.methodType(
                String.class, String.class, int.class);

        // MÔ PHỎNG JVM LINKAGE: gọi bootstrap trực tiếp.
        CallSite site = bootstrap(
                MethodHandles.lookup(),
                "renderScore",
                runtimeType,
                "report:",
                60);

        MethodHandle invoker = site.dynamicInvoker();
        System.out.println("invoker type: " + invoker.type());

        // Đối số runtime: user và score, không phải prefix/minimum.
        String first = (String) invoker.invokeExact("Lan", 75);
        String second = (String) invoker.invokeExact("Minh", 40);

        System.out.println("call 1: " + first);
        System.out.println("call 2: " + second);
        System.out.println("bootstrap calls: " + bootstrapCalls);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BootstrapArgumentsDemo.java
java BootstrapArgumentsDemo
~~~

Stdout dự kiến:

~~~text
bootstrap name: renderScore
bootstrap type: (String,int)String
static arguments: report: | 60
invoker type: (String,int)String
call 1: report:Lan=75 PASS
call 2: report:Minh=40 RETRY
bootstrap calls: 1
~~~

### Cách đọc kết quả

**Bước 1 — cấu hình linkage:** chương trình mô phỏng cung cấp `invokedName = "renderScore"`, `invokedType = (String,int)String` và hai giá trị `"report:"`, `60`. Đây là lần **gọi bootstrap bằng source code**, nhằm mô phỏng dữ liệu mà JVM cung cấp trong linkage của một site thực; số lần chạy ở ví dụ được quyết định bởi đúng **một lời gọi Java trực tiếp** trong `main`.

**Bước 2 — raw method handle:** method `render` khai báo bốn tham số `(String,int,String,int)String`. Hai tham số đầu là cấu hình, hai tham số cuối là dữ liệu nghiệp vụ.

**Bước 3 — bind static configuration:** `insertArguments(raw, 0, prefix, minimum)` gắn hai giá trị đầu. Handle mới `bound` có kiểu `(String,int)String`, khớp `runtimeType`. Static arguments không xuất hiện trong danh sách tham số runtime của site.

**Bước 4 — tạo CallSite:** `new ConstantCallSite(bound)` giữ target ổn định. `site.dynamicInvoker()` là handle với đúng `MethodType` này.

**Bước 5 — invocation:** hai lượt truyền `("Lan",75)` và `("Minh",40)`. Target tái sử dụng `prefix="report:"` và `minimum=60` đã gắn ở bước xây handle; chỉ `user` và `score` là dữ liệu mỗi lời gọi.

**Giới hạn của ví dụ:** `bootstrap calls: 1` **không chứng minh** một JVM invokedynamic BSM thực chỉ được thực thi đúng một lần trong mọi tình huống. Bởi ở đây chúng ta chủ động gọi method bootstrap một lần; JVM liên kết `invokedynamic` có các quy tắc riêng và có thể có cạnh tranh khi liên kết đồng thời. Ngoài ra, các phép nối chuỗi bên trong Java 17 có thể được compiler tự biên dịch thành những `invokedynamic` **khác**, không phải call site do đoạn mô phỏng tạo ra.

## 8. Ví dụ Java 17+ hoàn chỉnh 2: javac tạo invokedynamic cho nối chuỗi

Lần này ta viết Java thông thường rồi **quan sát bytecode thật**. Java 17 mặc định thường biên dịch phép nối chuỗi bằng `invokedynamic` kết hợp `java.lang.invoke.StringConcatFactory`.

Tạo file **StringConcatIndyDemo.java**:

~~~java
public class StringConcatIndyDemo {
    public static String describe(String user, int score) {
        return "user=" + user + "; score=" + score;
    }

    public static void main(String[] args) {
        System.out.println(describe("Lan", 81));
        System.out.println(describe("Minh", 40));
    }
}
~~~

Chạy:

~~~bash
javac StringConcatIndyDemo.java
java StringConcatIndyDemo
~~~

Stdout dự kiến:

~~~text
user=Lan; score=81
user=Minh; score=40
~~~

Xem bytecode chi tiết:

~~~bash
javap -c -v StringConcatIndyDemo
~~~

Trong output `javap`, tìm phương thức `describe`, dòng `invokedynamic` và phần `BootstrapMethods`. Một bản trích minh họa **về hình dạng**, lược bỏ constant-pool indexes vì số `#...` được compiler gán và có thể thay đổi:

~~~text
public static java.lang.String describe(java.lang.String, int);
  ...
    aload_0
    iload_1
    invokedynamic ... // makeConcatWithConstants:
                      // (Ljava/lang/String;I)Ljava/lang/String;
    areturn

BootstrapMethods:
  ...
  REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants
  Method arguments:
    user=\u0001; score=\u0001
~~~

Đây **không phải bản chép chính xác toàn bộ stdout của `javap`**; nó minh họa các trường cần định vị. Chỉ số `#...`, offset bytecode, cách in các ký tự điều khiển và một số chi tiết tối ưu có thể khác theo `javac`/JDK. Lệnh `java` ở trên mới có stdout hoàn chỉnh, xác định được để đối chiếu.

Các ý cần đọc từ trích đoạn:

- `aload_0` và `iload_1` lấy `user` và `score` của lượt gọi phương thức `describe`, nạp chúng lên operand stack.
- `invokedynamic` có descriptor `(Ljava/lang/String;I)Ljava/lang/String;`, nghĩa là **runtime invocation** nhận đúng một `String` và một `int`, trả `String`.
- BSM là `StringConcatFactory.makeConcatWithConstants`. Chữ `makeConcatWithConstants` không phải “dữ liệu user”; nó là tên liên quan cơ chế bootstrap cho phép nối chuỗi.
- Chuỗi recipe chứa `\u0001` là marker đại diện cho **một argument động**. Công thức `"user=\u0001; score=\u0001"` mô tả vị trí chèn hai runtime arguments; recipe là một **bootstrap argument tĩnh**.
- Với chương trình trên, recipe/configuration không cần thay đổi cho `"Lan",81` và `"Minh",40`. Runtime data thay đổi, nên hai chuỗi trả ra khác nhau.

### Recipe marker và static constants

`StringConcatFactory.makeConcatWithConstants` có quy ước dùng `\u0001` làm vị trí cho **argument runtime**; `\u0002` có thể chỉ một **hằng số bootstrap** khác cung cấp qua `constants` tùy theo recipe. Đó là quy ước **riêng của StringConcatFactory**, **không phải** quy tắc mọi BSM đều bắt buộc dùng ký tự đặc biệt.

Ví dụ khái niệm:

~~~text
recipe      = "user=\u0001, fixed=\u0002"
runtime arg = "Lan"
static arg  = "MODE-A"

result      = "user=Lan, fixed=MODE-A"
~~~

Đây chỉ là mô hình minh họa cách xử lý marker, không phải khẳng định `javac` sẽ sinh chính recipe đó từ chương trình trên. Phân biệt:

- `\u0001` đánh dấu **chỗ điền runtime argument**.
- `\u0002` đánh dấu **chỗ điền một bootstrap constant** trong recipe.
- Cả hai marker là **ký tự nằm trong recipe tĩnh**, nhưng chúng trỏ đến hai nguồn giá trị khác nhau trong quá trình tạo/vận hành phép nối chuỗi.

Nếu dùng `javap`, hãy nhìn cả **Method arguments** trong `BootstrapMethods` lẫn **descriptor** và các lệnh nạp giá trị trước `invokedynamic`. Chỉ đọc một phần sẽ khiến dễ nhầm recipe là một parameter runtime.

## 9. Bootstrap signature của StringConcatFactory và call-site signature

`StringConcatFactory` cung cấp BSM chuyên biệt (giản lược cú pháp API):

~~~java
CallSite makeConcatWithConstants(
        MethodHandles.Lookup lookup,
        String name,
        MethodType concatType,
        String recipe,
        Object... constants)
~~~

Trong trường hợp này:

**Bootstrap inputs:**

- `lookup`: do JVM cung cấp cho class chứa call site.
- `name`: tên điểm gọi, do JVM cung cấp.
- `concatType`: `(String,int)String`, từ descriptor của opcode.
- `recipe`: cấu hình nối chuỗi lấy từ `BootstrapMethods`.
- `constants` (nếu có): cấu hình cố định khác lấy từ bootstrap arguments.

**Runtime invocation inputs:**

- `user:String` và `score:int` được nạp lên operand stack trước `invokedynamic`.
- Kết quả target là một `String`.

Mặc dù có thể có cả `String recipe` lẫn `String user`, **không suy ra chúng cùng đi vào một slot**. `recipe` thuộc BSM, `user` thuộc descriptor runtime. BSM có quyền tạo target dùng recipe để xử lý các `user`/`score` sau này; JVM không tự trộn hai danh sách.

Mặt khác, `concatType` là **metadata về type**, không phải kết quả phép nối và cũng không phải một đối số nghiệp vụ tên `concatType` được target nhận. MethodType làm cầu nối từ linkage sang kiểm tra kiểu của target.

## 10. Ví dụ Java 17+ hoàn chỉnh 3: lambda capture là runtime argument của invokedynamic

Lambda là trường hợp rất dễ gây nhầm. Khi Java biên dịch một lambda có **captured variables**, `invokedynamic` được dùng ở **điểm tạo đối tượng lambda**. Giá trị captured (như `prefix`) được truyền như **runtime argument của chính opcode invokedynamic**, không phải một bootstrap static argument.

Sau đó khi bạn gọi phương thức của functional interface trên lambda object, lời gọi đó thường qua `invokeinterface` — **không phải là cùng opcode invokedynamic tạo lambda**.

Tạo file **LambdaCaptureDemo.java**:

~~~java
public class LambdaCaptureDemo {
    @FunctionalInterface
    interface Formatter {
        String apply(String value);
    }

    static Formatter make(String prefix) {
        return value -> prefix + value;
    }

    public static void main(String[] args) {
        Formatter hello = make("Hello ");
        Formatter welcome = make("Welcome ");

        System.out.println(hello.apply("Lan"));
        System.out.println(welcome.apply("Minh"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LambdaCaptureDemo.java
java LambdaCaptureDemo
~~~

Stdout dự kiến:

~~~text
Hello Lan
Welcome Minh
~~~

Xem class file:

~~~bash
javap -c -v LambdaCaptureDemo
~~~

Tìm method `make` và phần `BootstrapMethods`. Một sơ đồ bytecode rút gọn:

~~~text
make(String prefix):
    aload_0
    invokedynamic ... // apply:(Ljava/lang/String;)LLambdaCaptureDemo$Formatter;
    areturn

main(...):
    ...
    invokeinterface ... // LambdaCaptureDemo$Formatter.apply:(String)String
    ...

BootstrapMethods:
    REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
    arguments: samMethodType, implementationMethodHandle,
               instantiatedMethodType
~~~

Mã minh họa trên không cố tái hiện offset/index constant pool hay cú pháp descriptor chính xác của mọi dòng `javap`. Hãy chú ý bản chất:

1. **BSM là `LambdaMetafactory.metafactory`.** Các bootstrap static arguments mô tả kiểu abstract method của functional interface, `MethodHandle` cho phần triển khai lambda và kiểu method được hiện thực; chúng không phải bản thân giá trị `"Hello "` hoặc `"Welcome "`.
2. **`prefix` là captured runtime argument** của opcode `invokedynamic` tại `make`. Mỗi lượt gọi `make("Hello ")` hay `make("Welcome ")` cung cấp một `String` khác ở runtime để tạo ra lambda object có trạng thái capture tương ứng.
3. **`value` trong `hello.apply("Lan")` là argument của lời gọi `apply` sau đó**, không phải argument của `invokedynamic` đã tạo đối tượng `hello`. Đây là **hai thời điểm gọi khác nhau**: factory invocation để tạo lambda, rồi invocation của functional interface method để xử lý dữ liệu.
4. Thân lambda chứa phép nối chuỗi `prefix + value`; ở Java 17, compiler có thể tạo **một invokedynamic khác** cho thao tác nối chuỗi bên trong synthetic lambda method. Khi xem `javap`, cần đối chiếu mỗi `invokedynamic` với entry bootstrap tương ứng, không gộp `LambdaMetafactory` và `StringConcatFactory` thành một.
5. Giá trị capture tuy được giữ lâu trong đối tượng lambda sau khi tạo, **không biến thành static bootstrap argument**. “Được giữ lại” và “được ghi cố định trong class file” là hai khái niệm khác nhau.

Bảng so sánh:

| Giá trị | Thuộc lời gọi nào? | Đường đi |
| --- | --- | --- |
| Method type của SAM `Formatter.apply` | Bootstrap linkage của lambda factory | Bootstrap argument tĩnh |
| MethodHandle trỏ tới implementation lambda | Bootstrap linkage của lambda factory | Bootstrap argument tĩnh |
| `prefix="Hello "` | `invokedynamic` ở `make` | Runtime argument để tạo lambda |
| `prefix="Welcome "` | Lượt `invokedynamic` khác ở `make` | Runtime argument để tạo lambda |
| `"Lan"` | `hello.apply("Lan")` | Argument của `invokeinterface` sau khi lambda được tạo |
| `"Minh"` | `welcome.apply("Minh")` | Argument của `invokeinterface` sau khi lambda được tạo |

Đây là ví dụ cho thấy **cùng một thuật ngữ “argument” có thể tham chiếu tới nhiều lời gọi khác nhau**, cần xác định opcode/call site trước khi phân loại.

## 11. Công thức kiểm tra hai danh sách đối số từ bytecode

Khi đọc một lệnh `invokedynamic` trong `javap -v -c`, thực hiện theo thứ tự:

**A. Tìm dòng invokedynamic ở phương thức đang quan tâm.** Xác định nó làm gì: nối chuỗi, tạo lambda, hay liên kết một ngôn ngữ động. Không mặc định tất cả opcode có cùng BSM.

**B. Đọc descriptor của điểm gọi.** Với `(Ljava/lang/String;I)Ljava/lang/String;`, runtime arguments là `String` và `int`, return là `String`. Đây là số/kiểu dữ liệu được nạp/tiêu thụ trên operand stack mỗi lượt chạy.

**C. Quan sát lệnh ngay trước opcode.** Ví dụ `aload_0`, `iload_1`. Chúng có thể cho biết các giá trị đến từ local variable nào. Trên đường đi phức tạp, giá trị có thể được tính từ nhiều opcode trước đó; không chỉ đọc hai dòng gần nhất mà bỏ qua stack flow.

**D. Tìm bootstrap index của entry `CONSTANT_InvokeDynamic_info`.** Theo dõi tới phần `BootstrapMethods` để xác định `bootstrap_method_ref`.

**E. Đọc danh sách `Method arguments` của entry đó.** Đây là các static bootstrap arguments bổ sung. Với concat, thường có recipe; với lambda, thường có method types và implementation handle.

**F. Thêm ba thông số JVM-provided vào sơ đồ bootstrap.** Đừng quên `Lookup`, `name`, `MethodType`; chúng thường không hiện như ba phần tử “Method arguments” trong bảng `BootstrapMethods`, nhưng JVM vẫn cung cấp cho BSM.

**G. Kiểm tra BSM trả về CallSite với type nào.** Nếu đang tự triển khai BSM, kiểm tra `callSite.type().equals(invokedType)`. Với class file được compiler sinh, xem descriptor thực tế và API của factory tương ứng.

**H. Đối chiếu thay đổi theo từng lượt thực thi.** Thử hai giá trị runtime khác nhau trong cùng call site; nếu output khác, đừng suy ra BSM được chạy lại. Nhiều target dùng cấu hình linkage cố định để xử lý dữ liệu động.

### Mẫu bảng để ghi chú khi điều tra

| Field cần ghi | Ví dụ concat |
| --- | --- |
| Class/method chứa opcode | `StringConcatIndyDemo.describe` |
| Opcode | `invokedynamic` |
| Name/descriptor | `makeConcatWithConstants : (String,int)String` |
| BSM | `StringConcatFactory.makeConcatWithConstants` |
| Bootstrap static args | Recipe `"user=\u0001; score=\u0001"` |
| JVM-provided BSM args | `Lookup`, name, `MethodType` |
| Runtime arguments | `user:String`, `score:int` |
| Ai cung cấp runtime args? | Bytecode nạp hai local values lên operand stack |
| Target nhận gì? | Hai giá trị runtime theo descriptor |
| Giá trị kết quả | Một `String` từ target |

Với các ví dụ của `LambdaMetafactory`, ghi rõ “runtime args của **lambda factory invokedynamic**” và “args của **SAM invocation**” trong hai dòng riêng.

## 12. Không nhầm bootstrap method với chính target handle

Một bootstrap method có thể:

- Tìm direct method handle bằng `lookup.findStatic(...)`.
- Gắn giá trị cấu hình bằng `MethodHandles.insertArguments(...)`.
- Thích nghi chữ ký bằng `asType(...)` khi có chuyển đổi hợp lệ.
- Chọn một `ConstantCallSite` hoặc thiết lập một `MutableCallSite`.
- Trả về một `CallSite` để JVM liên kết điểm gọi.

**BSM không bắt buộc chính là method được gọi vào mỗi lượt runtime.** Nó là *factory/linker* tạo ra cấu trúc gọi. Chính `CallSite.target` hoặc dynamic invoker của call site mới đại diện cho hành vi sẽ thực thi ở các lần gọi tiếp theo.

Ví dụ conceptual:

~~~text
Bootstrap:
  bootstrap(Lookup, "calculate", (int)int, "fast")
    └── cấu hình "fast" để chọn target
         └── trả ConstantCallSite(target: (int)int)

Invocation 1:
  invokedynamic với runtime int=4
    └── target(4) -> kết quả

Invocation 2:
  invokedynamic với runtime int=9
    └── target(9) -> kết quả
~~~

Trong sơ đồ này, `"fast"` là bootstrap argument **cấu hình**; `4` và `9` là runtime arguments. Nếu sau đó cần sửa target, với `ConstantCallSite` target ổn định; với `MutableCallSite` hoặc `VolatileCallSite` có thể có cơ chế cập nhật target theo hợp đồng class đó, nhưng việc retarget **không đòi tự động chạy lại BSM**.

`CallSite` được thiết kế để có kiểu target tương thích với type của call site. Với `MutableCallSite`, khi cập nhật bằng `setTarget`, type của target mới phải đúng với call site; sự thay đổi hành vi không được tự đổi descriptor của lệnh `invokedynamic`.

## 13. Những lỗi thường gặp khi tự tạo bootstrap hoặc đọc bytecode

| Hiện tượng/nhầm lẫn | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Tưởng `bootstrap_arguments[]` chứa `user` và `score` | Đọc recipe mà bỏ qua operand stack và descriptor | Tách static BSM data khỏi runtime invocation data |
| Nghĩ JVM truyền recipe cho target như tham số đầu | Nhầm chữ ký BSM với chữ ký call site | Đọc `invokedType`, kiểm tra target type sau binding/adaptation |
| Dùng `(Lookup,String,MethodType,...)` làm signature runtime | Nhầm signature của linker với signature opcode | Call-site descriptor chỉ mô tả runtime inputs và return |
| Không thấy ba thông số JVM-provided trong `Method arguments` | Ba thông số đầu không phải static args bổ sung trong array | Ghi rõ `Lookup`, `name`, `type` vào sơ đồ BSM |
| Chạy cùng opcode nhiều lần thì nghĩ bootstrap chạy từng lượt | Nhầm linkage với invocation | Kiểm tra mô hình call site: liên kết khi cần, dùng target sau đó |
| Quá tin “bootstrap luôn chạy đúng 1 lần” | Không xét khả năng cạnh tranh linkage | Không đưa side effect “phải đúng một lần” vào BSM khi cần tính đúng |
| Target type khác site descriptor | Chưa bind/thích nghi đủ tham số | So `target.type()` với `invokedType` trước khi trả `CallSite` |
| BSM lỗi nhưng chỉ thử sửa runtime argument | Lỗi linkage khác lỗi dữ liệu mỗi lần gọi | Phân biệt `BootstrapMethodError` với ngoại lệ target/runtime |
| Lambda capture bị coi là bootstrap static argument | Thấy prefix được giữ trong lambda object | Quan sát `aload_0` trước lambda factory `invokedynamic` |
| `lambda.apply(x)` bị gọi là “invoke dynamic” của factory | Không phân biệt bước tạo lambda và bước dùng lambda | Dùng `javap` tách `invokedynamic` và `invokeinterface` |
| BSM cho String concat bị nhầm với BSM cho Lambda | Cùng class có nhiều opcode invokedynamic | Theo từng bootstrap index và bootstrap method ref riêng |
| Không thấy `invokedynamic` trong bytecode mong đợi | Compiler/JDK/optimization hoặc lệnh đã biến đổi | Dùng JDK 17 chuẩn, kiểm tra `javap -c -v` và method cụ thể |
| Tin static argument “luôn là Java field static” | Tên gọi dễ gây hiểu nhầm | Static argument ở đây là cấu hình cố định lưu trong class-file metadata |
| Lấy `MethodType` như thể chứa giá trị input | Đánh đồng kiểu và đối tượng thực tế | `MethodType` chỉ lưu types, values đến từ stack |
| Tưởng invokedynamic có receiver ẩn | Áp quy tắc `invokevirtual` sang invokedynamic | Mọi tham số runtime đều thể hiện trong descriptor |
| Quên void/no-argument call site | Cho rằng phải có runtime arguments | Descriptor có thể `()void`, `()String`... dù BSM có cấu hình |

## 14. Câu hỏi tự kiểm tra có đáp án

**1. Điểm khác nhau cơ bản giữa bootstrap arguments và invocation arguments?**  
Bootstrap arguments phục vụ **liên kết/cấu hình** call site; invocation arguments là **giá trị runtime** mà target xử lý mỗi lần opcode chạy.

**2. Một BSM nhận `Lookup`, `String name`, `MethodType`. Ba giá trị này có nằm trong `bootstrap_arguments[]` không?**  
Không. Đó là ba thông số chuẩn JVM cung cấp. `bootstrap_arguments[]` chứa **các đối số bổ sung** được ghi trong class file.

**3. Call site `(String,int)String` có static argument `"prefix"`. Khi gọi target, caller phải truyền mấy tham số runtime?**  
Hai: `String` và `int`. `"prefix"` có thể đã được BSM bind/chọn target, nhưng không tự làm tăng `parameterCount()` của call site.

**4. Vì sao `StringConcatFactory` nhận recipe nhưng `invokedynamic` chỉ truyền `user` và `score`?**  
Recipe là cấu hình của BSM, mô tả cách ghép các runtime values; nó không phải input slot trong call-site descriptor.

**5. Nếu code nạp một literal `"Lan"` lên stack ngay trước `invokedynamic`, `"Lan"` là loại argument nào?**  
Là **runtime invocation argument** của opcode. “Runtime” mô tả con đường truyền dữ liệu tại thời điểm thực thi, không đòi giá trị bắt buộc biến động.

**6. `MethodType` nhận tại bootstrap có chứa `"Lan"` không?**  
Không. Nó có thể mô tả `String.class` ở một parameter slot, không lưu giá trị.

**7. BSM trả về `ConstantCallSite`, thì mỗi lượt gọi có tự chạy lại BSM không?**  
Không phải theo cơ chế bình thường sau linkage: runtime dùng target đã liên kết. Tuy nhiên không được dựa vào số lần bootstrap side effect bằng đúng 1 trong mọi tình huống cạnh tranh.

**8. Lambda `prefix -> ...` có captured variable `prefix`. Tại sao `prefix` không phải bootstrap static arg?**  
Giá trị `prefix` được nạp lúc **lambda factory invokedynamic** chạy, tức là runtime argument của chính opcode đó. Bootstrap static args mô tả kiểu SAM/implementation và các cấu hình compiler ghi trong class file.

**9. Khi gọi `formatter.apply("Lan")`, `"Lan"` có phải argument của invokedynamic tạo lambda trước đó không?**  
Không. Đây là đối số của một lời gọi `apply` sau khi lambda object đã tồn tại; thường bytecode là `invokeinterface`.

**10. Mismatch type của CallSite với descriptor và dữ liệu runtime không hợp lệ khác nhau thế nào?**  
Mismatched call-site type là lỗi **linkage/thiết lập target**; dữ liệu runtime không hợp lệ là lỗi khi **target chạy**, ví dụ parse thất bại.

**11. Với `invokedynamic ()String`, bootstrap có thể nhận static arguments không?**  
Có. Runtime invocation không có đối số, nhưng BSM vẫn có thể được cấu hình bằng hằng số.

**12. Tại sao không đọc mỗi `BootstrapMethods` mà bỏ qua opcode?**  
Vì `BootstrapMethods` cung cấp thông tin linker và static configuration; số/kiểu runtime arguments nằm ở **descriptor** của `invokedynamic` và giá trị thực được nạp bởi bytecode trước đó.

**13. Khi BSM dùng `insertArguments` để gắn hai static values, target cuối có thể nhận ít tham số hơn raw method không?**  
Có. Raw handle có thể là `(String,int,String,int)String`, sau bind cấu hình còn `(String,int)String`, khớp runtime invocation.

**14. `MutableCallSite.setTarget` có khiến JVM phải chạy lại BSM hay đổi descriptor không?**  
Không. Đổi target theo hợp đồng call site nhưng giữ nguyên type; bản thân BSM không tự được chạy lại bởi thao tác retarget.

**15. Hai opcode invokedynamic trong cùng class có chắc dùng chung static arguments không?**  
Không. Phải theo từng constant-pool entry và bootstrap method index. Cùng BSM cũng có thể được cấu hình bằng các bootstrap arguments khác nhau.

## 15. Checklist thực hành khi debug invokedynamic

- [ ] Xác định **đúng một opcode** `invokedynamic` đang phân tích.
- [ ] Ghi `name` và **descriptor** của call site; chuyển descriptor thành `MethodType` để biết runtime inputs và return.
- [ ] Nhìn bytecode trước opcode để xác định **nguồn operand-stack values**.
- [ ] Theo bootstrap index tới `BootstrapMethods`, xác định **bootstrap_method_ref**.
- [ ] Ghi riêng danh sách **bootstrap_arguments[]** của entry tương ứng.
- [ ] Bổ sung `Lookup`, `name`, `MethodType` là ba giá trị **JVM-provided** khi mô tả lời gọi BSM.
- [ ] Phân biệt **BSM signature**, **raw target signature** và **call-site target signature**; chúng không buộc giống nhau.
- [ ] Kiểm tra `CallSite.type()` và `target.type()` phù hợp descriptor cuối.
- [ ] Nếu có capture hoặc adapter, ghi rõ **giá trị nào được gắn** và **giá trị nào còn truyền mỗi lượt**.
- [ ] Nếu class có cả lambda và nối chuỗi, phân tích các entry `LambdaMetafactory` và `StringConcatFactory` riêng.
- [ ] Phân biệt lỗi **linkage** và lỗi **runtime target**.
- [ ] Đừng suy luận số lần BSM chạy từ số lần in output của target.

## 16. Kết luận

`invokedynamic` có hai giai đoạn mang ý nghĩa khác nhau: **liên kết** bằng bootstrap method, rồi **thực thi** bằng target của call site. Trong linkage, JVM truyền `Lookup`, tên và `MethodType`; class file cung cấp thêm các **bootstrap static arguments** để cấu hình target. Trong invocation, JVM truyền **runtime arguments lấy từ operand stack** theo descriptor của điểm gọi, và target trả kết quả tương ứng.

Vì vậy, để trả lời câu hỏi “tham số này truyền lúc nào?”, cần xác định **tham số thuộc chữ ký của BSM, thuộc `BootstrapMethods`, hay thuộc descriptor của invokedynamic**. Ngay cả khi cả ba có cùng kiểu `String`, chỉ cần phân biệt nguồn và thời điểm dùng là có thể đọc đúng bytecode, viết BSM hợp lệ và tránh nhầm giá trị lambda capture/concat recipe với đối số nghiệp vụ.
