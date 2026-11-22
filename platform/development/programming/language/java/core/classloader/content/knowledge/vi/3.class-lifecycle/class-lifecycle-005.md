# Preparation: cấp phát và thiết lập giá trị mặc định cho static field

## 1. Preparation nằm ở đâu trong vòng đời lớp?

Khi JVM cần sử dụng một class hoặc interface, một phần công việc của nó gồm **Loading → Linking → Initialization**. **Preparation (chuẩn bị)** là một công đoạn thuộc **Linking**, sau khi JVM kiểm tra tính hợp lệ của class và trước khi class được khởi tạo.

~~~text
           Loading
     (tạo biểu diễn lớp từ bytecode)
                │
                ▼
           Linking
       ┌─────────────────┐
       │ Verification    │  Kiểm tra tính hợp lệ của bytecode
       │ Preparation     │  Tạo static field, đặt giá trị mặc định
       │ Resolution      │  Liên kết các tham chiếu ký hiệu khi cần
       └─────────────────┘
                │
                ▼
         Initialization
       (gán hằng ConstantValue theo quy tắc JVM;
        chạy <clinit> nếu có)
                │
                ▼
         Sử dụng lớp
~~~

Sơ đồ biểu diễn **các công việc về mặt khái niệm**: JVM có thể thực hiện *resolution* sớm hoặc trì hoãn theo từng tham chiếu; không phải mọi tham chiếu đều được resolve xong trước khi bắt đầu chạy chương trình. Điều bắt buộc là class/interface phải được **verify và prepare trước khi initialize**.

**Preparation làm gì?** JVM tạo nơi lưu trữ các field `static` do class/interface khai báo và gán **giá trị mặc định của kiểu** cho chúng. Phần này không chạy mã Java do lập trình viên viết, không gọi constructor và không thực thi những biểu thức phía sau dấu `=` trong khai báo field.

Ví dụ về các khai báo:

~~~java
static int count = 100;
static boolean ready = true;
static Object cache = new Object();
~~~

Sau Preparation, theo mô hình giá trị mặc định, các field lần lượt có giá trị **`0`, `false`, `null`**. Khi **Initialization** diễn ra, các biểu thức khai báo mới lần lượt gán `100`, `true`, và tham chiếu tới đối tượng mới.

Đó là sự phân biệt cốt lõi: **Preparation đặt trạng thái ban đầu theo kiểu; Initialization thực hiện mã tạo trạng thái mà ứng dụng mong muốn.**

## 2. JVM cấp phát static field và gán mặc định như thế nào?

Một field được khai báo `static` gắn với **class/interface đã được định nghĩa trong JVM**, không gắn với từng instance của class. Trong giai đoạn Preparation, JVM tạo các ô lưu trữ tương ứng và đặt mặc định theo kiểu:

| Loại field `static` | Giá trị mặc định sau Preparation | Ví dụ |
|---|---|---|
| `byte`, `short`, `int`, `long` | Số nguyên `0` tương ứng với kiểu | `static long timeout = 99L;` → trước initializer là `0L` |
| `float`, `double` | Số thực `+0.0` tương ứng với kiểu | `static double rate = 1.5;` → trước initializer là `0.0` |
| `char` | Ký tự null `'\u0000'` (mã Unicode U+0000) | `static char marker = 'A';` |
| `boolean` | `false` | `static boolean ready = true;` |
| Kiểu tham chiếu (ví dụ `String`, `Integer`, mảng, đối tượng) | `null` | `static String title = "Hello";` |
| Field `static` không khai báo initializer | Vẫn là giá trị mặc định sau cả Initialization, trừ khi có lệnh gán ở nơi khác | `static int attempts;` giữ `0` |

Lưu ý:

- Những giá trị này là **mặc định do ngữ nghĩa Java/JVM quy định**, không phải dữ liệu rác hay ngẫu nhiên.
- `static String text = "abc";` có giá trị `null` tại Preparation; gán tham chiếu chuỗi diễn ra ở Initialization. Tương tự `static Object value = new Object();` chưa gọi `new Object()` trong Preparation.
- `static int[] numbers = new int[3];`: **field tham chiếu mảng** mặc định là `null` tại Preparation. Mảng ba phần tử chỉ được tạo khi biểu thức `new int[3]` được thực thi ở Initialization; bản thân các phần tử của mảng mới có mặc định `0`.
- Field **không có `static`** thuộc mỗi đối tượng riêng. Nó nhận giá trị mặc định khi cấp phát instance theo quy trình tạo đối tượng, **không phải** khi JVM Preparation một class.
- Mô tả “static nằm chính xác ở Metaspace” hoặc “static nhất định nằm trong Method Area vật lý” dễ gây hiểu sai. Đặc tả định nghĩa **ngữ nghĩa lưu trữ và giá trị**, còn chi tiết bố trí bộ nhớ là quyết định triển khai JVM. Metaspace trong HotSpot chủ yếu chứa metadata của lớp; không đồng nhất mọi static field với vùng Metaspace.

Preparation còn có thể chuẩn bị một số cấu trúc nội bộ (chẳng hạn bảng hỗ trợ gọi phương thức). Đó là công việc của JVM, không phải việc thực thi `static { ... }` của chương trình.

## 3. Phân biệt Preparation, Initialization và thứ tự gán

Xem class sau dưới góc độ ba mốc thời gian:

~~~java
class Settings {
    static int attempts;               // Không có initializer
    static long timeout = 5000L;       // Có initializer
    static boolean enabled = true;     // Có initializer
    static String region = "ap-south"; // Có initializer

    static {
        System.out.println("Settings initialized");
    }
}
~~~

**Tại Preparation:**

~~~text
attempts = 0
timeout  = 0L
enabled  = false
region   = null
~~~

**Trong Initialization:**

1. Giá trị mặc định vẫn tồn tại khi bắt đầu khởi tạo.
2. JVM thực hiện các static field initializer và static block theo thứ tự xuất hiện trong mã nguồn sau khi đã xử lý các bước khởi tạo đặc biệt (nếu có).
3. `timeout` trở thành `5000L`, `enabled` thành `true`, `region` thành `"ap-south"`.
4. Static block in dòng `Settings initialized`; `attempts` vẫn là `0` vì không có mã nào gán giá trị khác.

**Sau Initialization thành công:** các field có trạng thái mà các initializer và static block đã xây dựng. Không nên hiểu Preparation là chạy `static { ... }`, cũng không nên cho rằng Java bỏ qua giá trị mặc định chỉ vì field có khai báo `= ...`.

Một chi tiết quan trọng: mã đang chạy **ngay trong quá trình khởi tạo của class** đôi khi có thể thấy các field chưa được gán bằng initializer và vẫn giữ giá trị mặc định. Đây là cơ chế sẽ được kiểm chứng trong ví dụ bên dưới, **không đồng nghĩa** với việc mã ứng dụng có thể tự do đọc static field trước khi class được khởi tạo.

## 4. Ví dụ Java 17+: thấy giá trị mặc định khi Initialization đang diễn ra

Ví dụ gồm một file nguồn độc lập **`PreparationDemo.java`**. Class lồng `Data` có các field được khai báo theo thứ tự có chủ ý.

~~~java
public class PreparationDemo {
    static class Data {
        // Không có initializer: sau Preparation là 0 và tiếp tục giữ 0.
        static int neverAssigned;

        // Hàm này chạy khi Initialization bắt đầu; các field bên dưới
        // chưa chạy initializer nên vẫn đang giữ giá trị mặc định.
        static int amount = calculate();

        static long timeout = 99L;
        static boolean enabled = true;
        static String label = "ready";

        // Hằng số nguyên thủy được biên dịch thành ConstantValue.
        static final int LIMIT = 42;

        // Integer không phải "constant variable" của Java.
        static final Integer WRAPPED = Integer.valueOf(42);

        static {
            System.out.println("Static block: initialization complete");
        }

        private static int calculate() {
            System.out.println(
                "While initializing: timeout=" + timeout
                + ", enabled=" + enabled
                + ", label=" + label
            );
            return 7;
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
            "PreparationDemo$Data",
            false,
            PreparationDemo.class.getClassLoader()
        );

        System.out.println("Loaded type: " + type.getName());

        // Hằng compile-time được javac nhúng vào nơi sử dụng:
        // truy cập này không kích hoạt khởi tạo Data.
        System.out.println("Constant only: " + Data.LIMIT);

        // getstatic với field không phải constant variable:
        // điểm này làm Data phải được khởi tạo.
        System.out.println("Amount: " + Data.amount);

        System.out.println(
            "After initialization: timeout=" + Data.timeout
            + ", enabled=" + Data.enabled
            + ", label=" + Data.label
        );

        System.out.println("Unassigned: " + Data.neverAssigned);
        System.out.println("Wrapped: " + Data.WRAPPED);
    }
}
~~~

Từ thư mục chứa `PreparationDemo.java`, chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 PreparationDemo.java
java PreparationDemo
~~~

**Stdout:**

~~~text
Loaded type: PreparationDemo$Data
Constant only: 42
While initializing: timeout=0, enabled=false, label=null
Static block: initialization complete
Amount: 7
After initialization: timeout=99, enabled=true, label=ready
Unassigned: 0
Wrapped: 42
~~~

### Vì sao output theo đúng thứ tự này?

**Bước 1 — Nạp/liên kết mà chưa khởi tạo.** `Class.forName("PreparationDemo$Data", false, loader)` yêu cầu tìm, nạp và liên kết class mà không chủ động initialize class đó. Chỉ in tên lớp **không phải** hoạt động khởi tạo class `Data`. Vì thế không có dòng output từ `calculate()` hoặc static block trước dòng `Loaded type`.

**Bước 2 — Đọc hằng số compile-time.** `Data.LIMIT` là một *constant variable* (`static final int` có initializer là biểu thức hằng). Với mã nguồn này, `javac` thay biểu thức sử dụng bằng giá trị `42` trong bytecode của caller; câu lệnh in hằng số không làm `Data` initialize. Đừng suy ra rằng *mọi* field `static final` đều hoạt động như vậy: `WRAPPED` là `Integer` nên không phải constant variable.

**Bước 3 — Truy cập `Data.amount`.** Đây là field `static` bình thường, nên việc đọc gây **active use** và JVM phải initialize `Data` trước khi cung cấp giá trị. Ở Preparation trước đó, `amount` và các field khác đều đã có mặc định theo kiểu.

**Bước 4 — Chạy `calculate()`.** Initializer đầu tiên là `amount = calculate()`. Lúc hàm chạy, các initializer khai báo ở phía dưới cho `timeout`, `enabled` và `label` **chưa chạy**, nên phương thức nhìn thấy `0`, `false`, `null`. Gọi phương thức này là hợp lệ: trình biên dịch hạn chế một số tham chiếu trực tiếp tới static field khai báo ở phía sau trong initializer, còn đọc thông qua một phương thức được gọi ở thời điểm chạy có thể thấy mặc định.

**Bước 5 — Hoàn tất Initialization.** JVM gán `amount = 7`, tiếp tục gán `timeout = 99L`, `enabled = true`, `label = "ready"`, tạo giá trị cho `WRAPPED`, rồi chạy static block. Sau đó `Data.amount` trả về `7` cho câu lệnh đang chờ ở `main`.

**Bước 6 — Field không có initializer.** `neverAssigned` vẫn là `0`, chứng minh chương trình **không cần** tự viết `= 0` để có mặc định. Khi class đã khởi tạo xong, mọi lần truy cập tiếp theo trong ví dụ đều đọc trạng thái sau khởi tạo.

> **Giới hạn thí nghiệm:** Dòng `While initializing...` được in **trong Initialization**, khi vài initializer chưa chạy; nó không phải câu lệnh Java chạy *trong Preparation*. Theo cách sử dụng Java thông thường, một lệnh đọc `static` không phải hằng sẽ kích hoạt khởi tạo lớp trước khi trả kết quả, nên khó thể đọc trực tiếp và riêng biệt trạng thái Preparation từ mã ứng dụng.

## 5. Lưu ý về `static final` và `ConstantValue`

Đây là điểm dễ bị giải thích sai khi học Preparation. Hãy so sánh:

~~~java
static final int MAX_USERS = 100;
static final String NAME = "demo";
static final int COMPUTED = Integer.parseInt("100");
static final Integer BOXED = 100;
static final int[] VALUES = {1, 2, 3};
~~~

| Khai báo | Có phải Java *constant variable*? | Cách tạo giá trị |
|---|---|---|
| `MAX_USERS` | Có: `final`, kiểu nguyên thủy, biểu thức hằng | `javac` thường sinh thuộc tính `ConstantValue` |
| `NAME` | Có: `final String`, biểu thức hằng | `javac` thường sinh `ConstantValue` |
| `COMPUTED` | Không: biểu thức gọi phương thức | Gán khi thực thi mã khởi tạo lớp |
| `BOXED` | Không: `Integer` không thuộc nhóm kiểu constant variable | Autoboxing/gọi `Integer.valueOf` khi thực thi khởi tạo |
| `VALUES` | Không: kiểu mảng | Mảng được tạo khi thực thi khởi tạo |

**Phân biệt chính xác theo JVMS Java 17:**

- **Preparation (`5.4.2):** JVM tạo các `static` field và đặt **giá trị mặc định**; không thực thi explicit initializer của Java.
- **Initialization (`5.5, bước 6):** các field `static final` có thuộc tính `ConstantValue` được gán giá trị hằng **ngay trước khi thực thi `<clinit>`** (và trước một số bước khởi tạo tiếp theo). Đây không phải việc chạy mã trong `<clinit>`.
- **Initialization (`5.5, bước 9):** JVM thực thi `<clinit>`, tương ứng với các phép gán static cần chạy mã và static block. Với Java source thông thường, `<clinit>` theo thứ tự khai báo.

Vì vậy câu “tất cả `static final` được gán ngay trong Preparation” là **quá rộng và không phản ánh đúng thứ tự trong JVMS Java 17**. Tài liệu nhập môn đôi khi gộp phần hằng `ConstantValue` vào sơ đồ Preparation để đơn giản hóa; khi cần độ chính xác đặc tả, hãy tách **default values của Preparation** khỏi **gán `ConstantValue` lúc bắt đầu Initialization**.

Đặc biệt, việc caller in `MAX_USERS` mà không kích hoạt class initialization **không chứng minh rằng lệnh truy cập đã đọc trực tiếp một field đang ở trạng thái Preparation**. Trình biên dịch có thể đã nhúng `100` vào bytecode của caller.

## 6. Tự kiểm tra bytecode với `javap`

Ví dụ bên trên sinh ít nhất hai tệp class:

~~~text
PreparationDemo.class
PreparationDemo$Data.class
~~~

Dùng lệnh dưới đây trong **Bash** hoặc **PowerShell** (dùng dấu nháy đơn để giữ nguyên ký tự `$`):

~~~bash
javap -v 'PreparationDemo$Data'
javap -c -p 'PreparationDemo$Data'
javap -c PreparationDemo
~~~

Điều nên tìm trong output (không phụ thuộc các số index của constant pool do `javac` chọn):

1. Field `LIMIT` có thông tin tương đương `ConstantValue: int 42`.
2. Phương thức `static {};` trong phần `javap -c -p` là `<clinit>` được biểu diễn dưới dạng static initializer; nó chứa việc gọi `calculate()` và các lệnh `putstatic` để gán field cần khởi tạo tại runtime.
3. Trong `PreparationDemo.main`, việc in `Data.LIMIT` không cần `getstatic` tới field `LIMIT`; hằng đã có thể được nhúng vào chuỗi của lệnh in hoặc dùng opcode đẩy hằng, tùy cách `javac` biên dịch biểu thức nối chuỗi.
4. Việc truy cập `Data.amount` sử dụng `getstatic`, làm JVM kiểm tra và bảo đảm `Data` đã được initialize trước khi giá trị được trả về.

**Cách đọc:** `javap` hiển thị bytecode/metadata của `.class`, **không hiển thị một “phương thức preparation”**. Preparation là thao tác của JVM khi linking; `<clinit>` là mã khởi tạo lớp được biên dịch từ các static initializer.

## 7. Hỏi đáp ngắn về ranh giới của Preparation

**Preparation có tạo instance của class không?** Không. Việc đặt giá trị mặc định cho `static` field không gọi constructor của class đó. Biểu thức như `new Object()` đặt trong static initializer chỉ được thực thi khi Initialization chạy.

**Preparation có chạy static block không?** Không. `static { ... }` góp vào `<clinit>` và chạy ở Initialization.

**`static final` có luôn là giá trị được “gán sẵn” không?** Không. Chỉ các hằng `static final` thuộc kiểu nguyên thủy hoặc `String` với initializer là **constant expression** mới là constant variable trong ngữ nghĩa Java. `static final List<?>`, `static final Integer`, `static final int[]`, hay `static final int` tính từ phương thức cần runtime initialization.

**Nếu chưa gán initializer thì JVM có bỏ qua field không?** Không. Field `static` vẫn tồn tại và có mặc định. Ví dụ `static String message;` có `null`, `static boolean active;` có `false`.

**Có phải `Class.forName("X", false, loader)` tức class X mới ở Loading, chưa có Preparation?** Không. Overload này yêu cầu tìm, nạp và liên kết nhưng **không chủ động khởi tạo** class được chỉ định. Loading và Preparation là hai công việc khác nhau; “chưa Initialization” không đồng nghĩa “chưa Linking”.

**Mỗi ClassLoader có một bộ static field không?** Chính xác hơn: mỗi class được **định nghĩa riêng** bởi một loader có trạng thái static của class đó. Hai loader định nghĩa hai class cùng tên nhị phân có thể tạo ra hai runtime type và các static field độc lập. Hai loader chỉ cùng trỏ tới **một class do parent định nghĩa** thì không tự sinh hai bộ static field.

**Khi nào Preparation có thể lỗi?** Các bước linking có thể ném `LinkageError` khi phát hiện ràng buộc kiểu không hợp lệ; cấp phát cấu trúc runtime có thể gặp `OutOfMemoryError`. Còn lỗi do chạy biểu thức initializer (ví dụ phép tính/gọi phương thức thất bại) thuộc **Initialization**, không được quy nhầm về Preparation.

**Các static field luôn tồn tại mãi đến khi JVM kết thúc?** Chúng thuộc vòng đời của class đã được định nghĩa. Class có thể trở thành đối tượng được giải phóng theo quy tắc class unloading khi classloader tương ứng không còn reachable và các điều kiện khác được thỏa mãn; thời điểm và khả năng giải phóng phụ thuộc JVM. `static` không có nghĩa là một vùng nhớ “vĩnh viễn” độc lập với vòng đời class.

## 8. Ba câu tự kiểm tra

**Câu 1.** Với `static int x = 9; static boolean ok;`, ngay sau Preparation giá trị mô hình của hai field là gì? Sau Initialization khi không có mã gán thêm cho `ok` thì sao?

**Đáp án:** Sau Preparation: `x = 0` và `ok = false`. Sau Initialization: `x = 9` và `ok = false`.

**Câu 2.** Vì sao trong ví dụ `Data`, `calculate()` thấy `timeout = 0` dù mã nguồn có `timeout = 99L`?

**Đáp án:** Preparation đã đặt `timeout = 0L`. Khi Initialization gọi `calculate()` cho field `amount`, initializer của `timeout` đứng phía sau chưa được thực thi. Phải đợi phương thức quay lại rồi JVM tiếp tục gán `99L`.

**Câu 3.** Vì sao lệnh in `Data.LIMIT` không kích hoạt Initialization, còn đọc `Data.amount` lại có thể kích hoạt?

**Đáp án:** `LIMIT` là compile-time constant và có thể được nhúng vào bytecode caller, vì thế câu lệnh đó không cần truy cập field bằng `getstatic`. `amount` là field static thông thường; việc đọc nó yêu cầu class đã initialize. Đây là quy tắc **active use**, không phải dấu hiệu rằng caller đã trực tiếp đọc bộ nhớ sau Preparation.

## 9. Nguồn đặc tả để đối chiếu

- [Java Virtual Machine Specification 17 — 5.4.2 Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2): tạo static field và đặt giá trị mặc định, không chạy explicit initializer.
- [Java Virtual Machine Specification 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): thứ tự gán `ConstantValue` và chạy `<clinit>`.
- [Java Language Specification 17 — 12.3.2 Preparation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3.2): liên hệ Preparation với class/interface.
- [Java Language Specification 17 — 12.4 Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): hành vi active use và thứ tự static initializer.

**Điểm cần nhớ:** Preparation tạo và đặt **giá trị mặc định cho static field**, còn hành vi đặt giá trị do source Java mô tả diễn ra khi Initialization; hằng `ConstantValue` có bước gán riêng khi bắt đầu Initialization theo JVMS.