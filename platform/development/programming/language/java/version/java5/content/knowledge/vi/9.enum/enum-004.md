# Quy tắc khởi tạo và tham chiếu trường `static` trong enum

## 1. Hằng enum cũng là đối tượng phải được khởi tạo

Khai báo:

```java
enum Phase {
    NEW("N"),
    RUNNING("R");

    private final String code;

    Phase(String code) {
        this.code = code;
    }
}
```

không chỉ định nghĩa hai tên. Java phải tạo hai đối tượng hằng, gọi constructor tương ứng và gán các tham chiếu vào những trường hằng của lớp enum.

Mỗi hằng enum có một trường ngầm định dạng `public static final` mang tên hằng. Các trường hằng này được xem là khai báo trước những trường `static` viết tường minh trong phần thân enum.

Đó là lý do một constructor enum không được tự do dùng mọi dữ liệu `static` của chính enum: constructor đang chạy có thể nằm ở thời điểm những dữ liệu đó chưa được khởi tạo xong.

Quy tắc nền tảng nằm trong [JLS §8.9.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.2) và [§8.9.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.3). Bài áp dụng cho Java hiện đại, với ví dụ chạy được từ Java 17.

## 2. Thứ tự cần hình dung khi enum bắt đầu được sử dụng

Ở mức cần cho bài này, có thể nhìn quá trình theo các bước:

1. Những trường được chuẩn bị với giá trị mặc định phù hợp; các biến hằng lúc biên dịch có quy tắc khởi tạo sớm riêng.
2. Các hằng enum được tạo theo thứ tự khai báo, chạy phần khởi tạo đối tượng và constructor cho từng hằng.
3. Các initializer của trường `static` thông thường và các khối `static` viết tường minh chạy theo thứ tự xuất hiện tương ứng trong phần thân lớp.
4. Khi khởi tạo thành công, mã sử dụng bình thường có thể làm việc với các hằng và dữ liệu `static` đã sẵn sàng.

Ví dụ với `NEW`, `RUNNING` rồi đến `BY_CODE = buildIndex()`, việc tạo `NEW` và `RUNNING` xảy ra trước lời gọi xây bảng `BY_CODE`.

Vị trí viết **định nghĩa constructor** không làm constructor chạy muộn hơn. Nó được gọi khi hằng tương ứng được tạo. Đưa một trường map lên trên phần mã constructor, nhưng vẫn trong phần thân sau danh sách hằng, không đưa map lên trước các hằng ngầm định.

Khởi tạo thành công diễn ra một lần cho mỗi danh tính lớp enum, không phải một lần mỗi khi đọc hằng. Các lớp cùng tên được nạp bởi những class loader khác nhau là một chủ đề khác; không nên diễn đạt thành “chỉ có đúng một lần cho mọi JVM và mọi class loader”.

## 3. Hạn chế truy cập trực tiếp từ constructor và phần khởi tạo đối tượng

Java báo lỗi biên dịch khi constructor, khối khởi tạo đối tượng hoặc initializer của trường đối tượng trong enum tham chiếu trường `static` của **chính enum đó**, trừ khi trường là một biến hằng (constant variable).

Ví dụ bị từ chối:

```java
import java.util.HashMap;
import java.util.Map;

enum BadPhase {
    NEW;

    static final Map<String, BadPhase> INDEX = new HashMap<>();

    BadPhase() {
        INDEX.put(name(), this); // Lỗi biên dịch.
    }
}
```

`INDEX` là trường `static final`, nhưng chưa được khởi tạo khi Java đang tạo `NEW`. Nếu cho truy cập như trên, chương trình có thể dùng một tham chiếu map còn `null`.

Cùng hạn chế áp dụng nếu đưa thao tác đó sang một khối khởi tạo đối tượng hoặc một biểu thức khởi tạo trường đối tượng. Đó vẫn là phần việc chạy khi tạo từng hằng, không phải giai đoạn sau khi toàn bộ enum đã sẵn sàng.

Các hằng enum khác cũng là trường `static` nhưng không phải biến hằng theo định nghĩa ở mục tiếp theo. Đừng so `this == Phase.NEW` ngay trong constructor để quyết định cách đăng ký; hãy truyền dữ liệu riêng cho từng hằng qua tham số constructor và xử lý quan hệ giữa các hằng ở giai đoạn phù hợp.

Quy tắc nói về trường `static` của chính enum, không phải một lệnh cấm mọi lời gọi hàm `static` trong constructor. Tuy nhiên, phụ thuộc sang một lớp khác vẫn có thể tạo vòng khởi tạo nếu thiết kế không cẩn thận.

## 4. `static final` chưa đủ để là biến hằng lúc biên dịch

Một biến hằng theo [JLS §4.12.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4) có kiểu nguyên thủy hoặc `String`, là `final` và được khởi tạo bằng biểu thức hằng phù hợp.

| Khai báo trường | Là biến hằng? | Có thể đọc trực tiếp trong constructor enum theo ngoại lệ này? |
| --- | --- | --- |
| `static final int LIMIT = 1 + 2;` | Có | Có |
| `static final String PREFIX = "phase";` | Có | Có |
| `static final Integer LIMIT = 3;` | Không | Không |
| `static final String PREFIX = new String("phase");` | Không | Không |
| `static final String PREFIX = makePrefix();` | Không | Không |
| `static final Map<String, Phase> INDEX = Map.of();` | Không | Không |

`final` trên một tham chiếu chỉ ngăn gán lại trường sau khi đã được gán theo quy tắc; nó không biến đối tượng được tham chiếu thành một hằng lúc biên dịch.

Ví dụ một chuỗi literal hằng có thể được constructor dùng dù khai báo nằm sau danh sách các hằng enum:

```java
enum Tagged {
    A;

    static final String PREFIX = "tag";
    final String tag;

    Tagged() {
        tag = PREFIX + ":" + name();
    }
}
```

Không suy ra rằng một `Integer` boxing hoặc một chuỗi được hàm trả về cũng có cùng ngoại lệ. Phân loại dựa vào kiểu và biểu thức khởi tạo, không chỉ dựa vào việc giá trị nhìn có vẻ cố định.

## 5. Gọi qua helper có thể qua compiler nhưng vẫn sai thời điểm

Một phương thức `static` có thể đọc trường `static`. Nếu constructor gọi phương thức đó, việc tham chiếu trường nằm trong thân phương thức, nên không nhất thiết bị chặn bởi cùng lỗi truy cập trực tiếp.

Điều đó không khiến trường được khởi tạo sớm hơn. Một helper được gọi ngay khi enum đang khởi tạo vẫn có thể thấy giá trị mặc định của trường chưa tới lượt khởi tạo.

Đặc biệt, quy tắc thường gặp “gọi phương thức static sẽ khởi tạo lớp trước” không có nghĩa lời gọi lồng ngay trong constructor sẽ buộc hoàn thành mọi phần còn lại của quá trình khởi tạo đang diễn ra trước khi helper chạy. Luồng hiện tại đang ở bên trong quá trình đó.

Vì vậy, không dùng helper chỉ để tránh thông báo lỗi của compiler. Cần sửa thứ tự và hướng phụ thuộc của thiết kế.

Một ví dụ lỗi chạy đầy đủ có ở mục 8. Nó dùng map còn `null` trong helper và thất bại ngay khi truy cập hằng lần đầu.

## 6. Cách tổ chức bảng tra cứu phù hợp

Một mẫu rõ ràng gồm hai giai đoạn:

1. Constructor chỉ chuẩn bị dữ liệu của từng hằng, chẳng hạn lưu `code` vào trường `final` của đối tượng.
2. Một initializer `static` sau các hằng duyệt `values()` để xây bảng tra cứu từ toàn bộ các hằng đã được tạo.

Luồng phụ thuộc:

```text
Tạo NEW với code N
        ↓
Tạo RUNNING với code R
        ↓
Duyệt các hằng để xây BY_CODE
        ↓
Dùng BY_CODE khi tra cứu bình thường
```

Tránh hướng ngược lại: constructor từng hằng dùng `BY_CODE`, trong khi việc tạo `BY_CODE` lại phụ thuộc vào các hằng chưa được tạo xong.

Có thể dùng một khối `static` hoặc một phương thức được gọi từ initializer của trường `static`. Điều quan trọng là **thời điểm gọi** ở sau giai đoạn tạo các hằng, không phải tên phương thức có chữ “init” hay không.

Nếu có nhiều trường `static` phụ thuộc nhau, tiếp tục tuân theo thứ tự khởi tạo tường minh của chúng. Một static block đọc trường được khởi tạo về sau vẫn có thể gặp lỗi phụ thuộc; “đã chuyển sang static block” không tự giải quyết mọi vòng khởi tạo.

## 7. Chương trình hoàn chỉnh: constructor trước, bảng tra cứu sau

Lưu vào `EnumInitializationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class EnumInitializationDemo {
    enum Phase {
        NEW("N"),
        RUNNING("R");

        static final String PREFIX = "phase";
        private static final Map<String, Phase> BY_CODE = buildIndex();
        private final String code;

        Phase(String code) {
            this.code = code;
            System.out.println("construct " + name() + " code=" + code + " prefix=" + PREFIX);
        }

        static {
            System.out.println("static block size = " + BY_CODE.size());
        }

        private static Map<String, Phase> buildIndex() {
            System.out.println("build index");
            Map<String, Phase> result = new HashMap<>();
            for (Phase phase : values()) {
                if (result.putIfAbsent(phase.code, phase) != null) {
                    throw new IllegalStateException("Duplicate code: " + phase.code);
                }
            }
            return Map.copyOf(result);
        }

        static Phase fromCode(String code) {
            Objects.requireNonNull(code, "code");
            Phase result = BY_CODE.get(code);
            if (result == null) {
                throw new IllegalArgumentException("Unknown code: " + code);
            }
            return result;
        }
    }

    public static void main(String[] args) {
        System.out.println("constant prefix = " + Phase.PREFIX);
        System.out.println("request RUNNING");
        Phase selected = Phase.RUNNING;
        System.out.println("selected = " + selected);
        System.out.println("lookup N = " + Phase.fromCode("N"));
        System.out.println("same constant = " + (selected == Phase.RUNNING));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```shell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 EnumInitializationDemo.java
java EnumInitializationDemo
```

Kết quả chuẩn:

```text
constant prefix = phase
request RUNNING
construct NEW code=N prefix=phase
construct RUNNING code=R prefix=phase
build index
static block size = 2
selected = RUNNING
lookup N = NEW
same constant = true
```

Đọc kết quả theo thứ tự:

- Đọc `Phase.PREFIX` là đọc biến hằng chuỗi, không kích hoạt toàn bộ khởi tạo enum trong trường hợp này.
- Truy cập `Phase.RUNNING` là lần sử dụng cần khởi tạo enum. Dù yêu cầu `RUNNING`, Java vẫn tạo `NEW` trước theo thứ tự khai báo.
- Cả hai constructor đã chạy trước `buildIndex`.
- Khối `static` ở phía sau đọc được bảng có hai mục vì initializer của `BY_CODE` đã hoàn tất.
- Những lần tra cứu hoặc đọc lại `Phase.RUNNING` không gọi lại constructor.

`buildIndex` còn kiểm tra mã trùng, rồi giữ một map không cho sửa để phục vụ tra cứu. Nó không phụ thuộc thứ tự duyệt của map; chỉ dùng tra cứu khóa và kích thước.

Nếu mã trùng làm `buildIndex` ném ngoại lệ trong lúc khởi tạo lớp, đó là lỗi khởi tạo enum, khác với `fromCode` ném `IllegalArgumentException` cho một yêu cầu tra cứu tên mã không có sau khi enum đã khởi tạo bình thường.

Constructor của enum không được là `public` hoặc `protected`. Không ghi access modifier thì constructor enum là `private`; mã ứng dụng không dùng `new` để tạo thêm hằng. Trong ví dụ, việc constructor được gọi cho từng hằng do khai báo enum và trình biên dịch quản lý.

## 8. Chương trình phản ví dụ: helper không sửa được vòng khởi tạo

Chương trình sau cố ý sai thời điểm phụ thuộc nhưng vẫn biên dịch. Lưu riêng vào `EnumInitializationFailureDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class EnumInitializationFailureDemo {
    enum Broken {
        A;

        private static final Map<String, Broken> INDEX = new HashMap<>();

        Broken() {
            register(this);
        }

        private static void register(Broken value) {
            INDEX.put(value.name(), value);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(Broken.A);
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first failure = " + ex.getClass().getSimpleName());
            System.out.println("cause = " + ex.getCause().getClass().getSimpleName());
        }
        try {
            System.out.println(Broken.A);
        } catch (NoClassDefFoundError ex) {
            System.out.println("second failure = " + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy riêng:

```shell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 EnumInitializationFailureDemo.java
java EnumInitializationFailureDemo
```

Kết quả chuẩn:

```text
first failure = ExceptionInInitializerError
cause = NullPointerException
second failure = NoClassDefFoundError
```

Điều xảy ra:

1. Đọc `Broken.A` bắt đầu khởi tạo lớp enum.
2. Constructor của `A` gọi `register(this)`.
3. `INDEX = new HashMap<>()` chưa tới lượt chạy; `INDEX` vẫn là `null`.
4. `INDEX.put(...)` gây `NullPointerException`.
5. Lỗi trong quá trình khởi tạo được phản ánh ra lần sử dụng đầu bằng `ExceptionInInitializerError` trong trường hợp này.
6. Lớp bị đánh dấu khởi tạo thất bại; lần dùng tiếp theo trong cùng ngữ cảnh nạp lớp không tự chạy lại toàn bộ để thử cứu map, mà có thể hiện `NoClassDefFoundError` như ví dụ.

Ở đây `NoClassDefFoundError` không có nghĩa tệp `.class` vừa biến mất. Cần đọc chuỗi nguyên nhân trước đó: lớp đã có lỗi khởi tạo.

Cách khắc phục là bỏ việc đăng ký từ constructor và xây chỉ mục sau các hằng, như chương trình đúng. Bắt lỗi rồi gọi lại cùng enum không sửa thứ tự phụ thuộc đã sai.

Quy trình đánh dấu và xử lý lỗi khởi tạo lớp được mô tả trong [JLS §12.4.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.2). Ví dụ dùng một `NullPointerException`, nên cần phân biệt nó với trường hợp initializer tự ném một đối tượng thuộc họ `Error`, vốn có quy tắc truyền ra tương ứng.

## 9. Khi nào bắt đầu khởi tạo và điều gì không phải bằng chứng đã sẵn sàng?

Các thao tác sử dụng thông thường như đọc một hằng enum hoặc gọi một phương thức `static` của enum từ bên ngoài có thể yêu cầu lớp enum được khởi tạo trước khi thao tác đó tiếp tục.

Ngược lại, việc tên enum xuất hiện trong khai báo biến không tự có nghĩa các constructor đã chạy:

```java
Phase variable;
```

Đọc biến hằng lúc biên dịch như `PREFIX` cũng không kích hoạt khởi tạo như việc đọc một trường `static` thông thường. Đây là lý do dòng đầu của chương trình đúng chưa xuất hiện log constructor.

Không viết logic phụ thuộc vào việc “một chỗ nào đó chắc đã đụng enum rồi”. Hãy xây dữ liệu `static` theo các phụ thuộc đúng ngay trong quy trình khởi tạo.

Với ứng dụng dùng nhiều luồng, quy trình khởi tạo lớp có cơ chế phối hợp riêng, nhưng điều đó không làm một vòng phụ thuộc khởi tạo trở nên đúng. Cũng không nên đưa `this` chưa hoàn tất khởi tạo ra ngoài constructor để một luồng khác sử dụng.

## 10. Cách rà soát mã khởi tạo enum

Có thể đi theo thứ tự sau:

1. Liệt kê các hằng theo đúng thứ tự khai báo và dữ liệu constructor của chúng.
2. Xác định những trường đối tượng/khối khởi tạo đối tượng chạy khi tạo từng hằng.
3. Xác định initializer của các trường `static` thông thường và khối `static` theo thứ tự khai báo.
4. Với mỗi constructor, kiểm tra cả lời gọi gián tiếp: helper có đọc map, gọi `values()` quá sớm hoặc tham chiếu hằng khác chưa sẵn sàng không?
5. Đưa bảng tra cứu/quy tắc giữa nhiều hằng sang bước sau khi các hằng đã được tạo.
6. Phân biệt trường `static final` với biến hằng thực sự; không coi wrapper hoặc collection là ngoại lệ được đọc sớm.
7. Kiểm chứng bằng một chương trình nhỏ có log nếu thứ tự chưa rõ, rồi loại bỏ log không cần thiết khỏi mã sử dụng thật.

Gọi `values()` trong bước xây bảng sau các hằng là phù hợp. Gọi nó từ constructor đang tạo một hằng có thể quá sớm vì toàn bộ cấu trúc chứa các hằng chưa hoàn tất. Tên phương thức không thay thế phân tích về thời điểm.

Không nên dùng constructor enum để truy cập cơ sở dữ liệu, gọi một dịch vụ cần enum đã sẵn sàng hoặc tự đăng ký vào cấu trúc của cùng enum chưa được tạo. Những phụ thuộc đó cần một giai đoạn hoặc thành phần có vòng đời rõ ràng hơn.

## 11. Những nhầm lẫn cần tránh

**“Trường static luôn sẵn sàng trước mọi constructor enum.”** Không. Các đối tượng hằng enum được tạo trong chính quá trình khởi tạo lớp, trước nhiều trường `static` tường minh của nó.

**“Chỉ cần thêm final là dùng được trong constructor.”** Không. Chỉ biến hằng theo định nghĩa của ngôn ngữ được ngoại lệ; `static final Map` hoặc `static final Integer` không thuộc trường hợp đó.

**“Gọi qua helper là cách sửa lỗi truy cập static.”** Không. Nó có thể đổi một lỗi bị compiler chặn thành một lỗi lúc chạy, nếu thời điểm phụ thuộc vẫn sai.

**“Dời khai báo map lên trên phần định nghĩa constructor là đủ.”** Không. Các trường hằng enum ngầm định vẫn đứng trước các trường `static` tường minh.

**“Truy cập riêng RUNNING chỉ tạo RUNNING.”** Không. Khi lớp enum được khởi tạo bình thường, các hằng được tạo theo thứ tự khai báo của enum.

**“Lần truy cập tiếp theo sẽ tự thử khởi tạo lại sau lỗi.”** Không. Không dùng cách đọc lại cùng lớp đã lỗi như một cơ chế thử lại. Cần sửa nguyên nhân và chạy trong ngữ cảnh lớp được nạp lại phù hợp khi phát triển.

## 12. Tự kiểm tra

**Câu 1.** Vì sao constructor enum được phép đọc `static final String PREFIX = "phase"`, nhưng không được đọc trực tiếp `static final Integer LIMIT = 3` của cùng enum?

`PREFIX` là biến hằng kiểu `String` khởi tạo bằng biểu thức hằng. `LIMIT` có kiểu wrapper, không phải biến hằng theo định nghĩa đó dù có `final`.

**Câu 2.** Nếu một map tra cứu được xây từ tất cả hằng enum, nên xây trong constructor từng hằng hay sau khi tạo các hằng?

Sau khi các hằng đã được tạo, bằng initializer của trường `static` hoặc khối `static` được tổ chức theo đúng phụ thuộc.

**Câu 3.** Vì sao helper `register` trong phản ví dụ vẫn gặp `INDEX == null`?

Nó chạy ngay từ constructor của hằng đầu, trước initializer của `INDEX`. Gọi gián tiếp không làm thời gian khởi tạo tiến tới phía sau.

**Câu 4.** `NoClassDefFoundError` ở lần dùng thứ hai có luôn nghĩa thiếu tệp class không?

Không. Trong ví dụ nó xuất phát từ việc lần khởi tạo trước thất bại. Cần xem lỗi gốc và chuỗi nguyên nhân.

**Câu 5.** Tại sao truy cập `RUNNING` đầu tiên vẫn tạo `NEW` trước?

Khởi tạo diễn ra cho lớp enum với các hằng theo thứ tự khai báo, không chỉ tạo tùy hằng mà biểu thức hiện tại yêu cầu.
