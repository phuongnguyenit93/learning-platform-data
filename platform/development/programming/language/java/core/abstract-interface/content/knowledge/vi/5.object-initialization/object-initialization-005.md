# Rủi ro gọi phương thức có thể bị ghi đè trong constructor của Java

## 1. Vấn đề cốt lõi

Trong Java, constructor có trách nhiệm đưa đối tượng về trạng thái hợp lệ trước khi mã bên ngoài bắt đầu sử dụng nó. Tuy nhiên, **nếu constructor của lớp cha gọi một phương thức instance có thể bị override**, Java vẫn thực hiện **phân phối động (dynamic dispatch)** đến phương thức được ghi đè ở lớp con, dù constructor của lớp con **chưa hoàn tất**, thậm chí những bộ khởi tạo trường của lớp con **chưa chạy**.

Hệ quả thường gặp: phương thức override đọc các trường của lớp con khi chúng còn giữ **giá trị mặc định** (`null`, `0`, `false`). Kết quả có thể là trạng thái sai, log sai, `NullPointerException`, vi phạm bất biến của đối tượng, hoặc hành vi khó tái hiện.

Quy tắc thực hành quan trọng nhất:

> **Không gọi phương thức có thể bị override trên `this` khi constructor đang chạy, kể cả gọi gián tiếp qua một phương thức khác.** Hãy hoàn tất khởi tạo trước rồi mới thực thi các bước mở rộng đa hình.

Vấn đề đặc biệt dễ gặp với **abstract class**, bởi constructor của lớp trừu tượng vẫn chạy khi tạo đối tượng lớp con; phương thức `abstract` khai báo trong lớp cha có thể bị gọi ngay từ constructor ấy và thực thi ở lớp con lúc lớp con chưa khởi tạo xong.

## 2. Vì sao có thể xảy ra? Kết hợp thứ tự khởi tạo với đa hình

Khi thực thi `new Derived()` với `Derived extends Base`, JVM tạo một đối tượng có kiểu thực tế là `Derived`, chứ không tạo trước một đối tượng `Base` độc lập rồi thay thế nó. Vùng nhớ cho các trường instance của **toàn bộ** đối tượng được cấp phát trước và có giá trị mặc định.

Với trường hợp kế thừa thông thường, không có lời gọi `this(...)` phức tạp:

1. **Cấp phát bộ nhớ** cho đối tượng `Derived` và gán giá trị mặc định cho các trường instance trên toàn chuỗi kế thừa: tham chiếu `null`, số `0`, `boolean` là `false`.
2. **Đi theo chuỗi constructor** từ lớp con lên `super(...)`; constructor của lớp cao nhất chạy trước. Đối với từng lớp, sau khi constructor lớp cha hoàn thành, các bộ khởi tạo trường instance và instance initializer block của lớp đó mới chạy theo thứ tự xuất hiện trong mã, rồi thực thi phần thân constructor của lớp đó.
3. Khi đang ở **constructor `Base`**, các trường của `Derived` vẫn chưa chạy initializer của `Derived` hoặc phần thân constructor `Derived`.
4. Nhưng nếu `Base` gọi một instance method có thể override, Java dùng **kiểu thực tế của đối tượng** để chọn bản override, nên có thể nhảy thẳng vào `Derived.method()`.
5. Chỉ sau khi constructor `Base` trả về, việc khởi tạo trường và phần thân constructor `Derived` mới tiếp tục.

Điều này không trái với nguyên tắc `super(...)` chạy trước: **thứ tự constructor** và **cơ chế chọn phương thức override** là hai quy tắc khác nhau. Lời gọi `super(...)` xác định cách khởi tạo phần lớp cha; nó không vô hiệu hóa virtual dispatch.

Giá trị mặc định có thể bị quan sát trong override ngay cả khi trường lớp con khai báo initializer tại nơi định nghĩa, chẳng hạn `private String name = "Đã sẵn sàng";`. Dòng gán ấy được thực thi **sau** khi constructor của lớp cha kết thúc.

Lưu ý: static initialization là cơ chế riêng của lớp và không thay đổi quy tắc nguy hiểm đối với các trường instance trong ví dụ này. Constructor có gọi `this(...)` sẽ ủy quyền sang constructor khác của cùng lớp; dù có biến thể thứ tự, invariant quan trọng vẫn giữ nguyên: **không giả định phần lớp con đã khởi tạo xong khi mã lớp cha đang chạy**.

## 3. Ví dụ Java 17+ tái hiện lỗi và cách sửa

Ví dụ sau đặt cả trường hợp nguy hiểm và cách tổ chức an toàn vào **một tệp `Main.java`**. Đầu tiên, constructor lớp cha gọi một phương thức `abstract` và bản override nhìn thấy `null`. Sau đó, phương án an toàn chỉ kiểm tra phần trạng thái mà chính lớp cha đã khởi tạo, rồi chạy hook của lớp con sau khi toàn bộ constructor hoàn tất.

```java
import java.util.Objects;

// CÁCH KHÔNG AN TOÀN: constructor gọi một phương thức overridable.
abstract class HazardBase {
    protected HazardBase() {
        System.out.println("1. HazardBase(): đang khởi tạo");
        printStatus(); // Dynamic dispatch xảy ra ngay tại đây.
    }

    protected abstract void printStatus();
}

final class HazardChild extends HazardBase {
    // Initializer này CHƯA chạy khi HazardBase() gọi printStatus().
    private String status = "ready";

    @Override
    protected void printStatus() {
        System.out.println("2. Override: status = " + status);
    }

    String getStatus() {
        return status;
    }
}

// CÁCH AN TOÀN: constructor chỉ xử lý phần trạng thái của lớp cha.
abstract class SafeBase {
    private final String category;

    protected SafeBase(String category) {
        this.category = Objects.requireNonNull(category, "category");
        verifyBaseState(); // private, không bị override.
    }

    private void verifyBaseState() {
        System.out.println("4. SafeBase(): category = " + category);
    }

    // Gọi phương thức đa hình sau khi đối tượng đã tạo xong.
    public final void start() {
        System.out.println("6. start(): category = " + category);
        perform();
    }

    protected abstract void perform();
}

final class SafeChild extends SafeBase {
    private final String status;

    SafeChild() {
        super("TASK");
        status = "ready";
        System.out.println("5. SafeChild(): status = " + status);
    }

    @Override
    protected void perform() {
        System.out.println("7. perform(): status = " + status);
    }
}

public class Main {
    public static void main(String[] args) {
        HazardChild hazard = new HazardChild();
        System.out.println("3. Sau new: status = " + hazard.getStatus());

        SafeChild safe = new SafeChild();
        safe.start();
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Đầu ra chính xác:

```text
1. HazardBase(): đang khởi tạo
2. Override: status = null
3. Sau new: status = ready
4. SafeBase(): category = TASK
5. SafeChild(): status = ready
6. start(): category = TASK
7. perform(): status = ready
```

**Phân tích dòng 1–3:**

- Trong `new HazardChild()`, constructor `HazardBase()` chạy trước; nó in dòng 1 rồi gọi `printStatus()`.
- `printStatus()` là phương thức trừu tượng ở lớp cha nhưng đã được `HazardChild` triển khai. Lời gọi chọn `HazardChild.printStatus()` theo kiểu thực tế của đối tượng.
- Khi override đọc `status` ở dòng 2, phép gán `"ready"` trong initializer của lớp con chưa được thực thi. Trường `String` đang là `null`.
- Sau khi constructor lớp cha trả về, initializer của `HazardChild` chạy và gán `status = "ready"`. Dòng 3 vì vậy in `ready`.
- Từ khóa `final` trên lớp `HazardChild` không giúp ngăn vấn đề, vì việc override đã diễn ra **giữa `HazardChild` và `HazardBase`**.

**Phân tích dòng 4–7:**

- `SafeBase()` chỉ gán trường của chính nó và gọi `verifyBaseState()` là `private`, nên phương thức này không thể bị lớp con override.
- `SafeChild()` tiếp tục khởi tạo `status` và kết thúc. Trong `main`, chỉ **sau khi `new SafeChild()` trả về**, chương trình mới gọi `safe.start()`.
- `start()` là `final`, giữ cố định thứ tự công việc; nó gọi hook `perform()` đa hình khi `status` đã là `"ready"`. Lúc này việc mở rộng qua lớp con là hợp lý.
- `final` chỉ ngăn override trực tiếp phương thức `start()`; nó **không tự khiến mọi lời gọi bên trong `start()` trở nên an toàn trong constructor**. Sự an toàn ở đây đến từ thời điểm gọi `start()` sau khởi tạo.

Ví dụ dùng `System.out.println` để quan sát chính xác thứ tự, nên không phụ thuộc lịch chạy luồng hoặc yếu tố ngẫu nhiên.

## 4. Lỗi thực tế có thể nghiêm trọng hơn giá trị `null`

### 4.1. `NullPointerException`

Một phương thức override có thể giả định trường lớp con đã được gán:

```java
// Đoạn minh họa bên trong một lớp con:
private String configuration = "production";

@Override
protected void printStatus() {
    System.out.println(configuration.length());
}
```

Nếu constructor lớp cha gọi `printStatus()` quá sớm, `configuration` vẫn là `null`. Lời gọi `configuration.length()` sẽ ném `NullPointerException` và việc tạo đối tượng thất bại. Vì đây chỉ là đoạn minh họa trong một lớp con giả định, nó không phải một tệp Java độc lập; ví dụ `Main.java` ở trên mới là chương trình có thể chạy trực tiếp.

### 4.2. Giá trị mặc định trông có vẻ hợp lệ

Với trường số nguyên hoặc boolean, lỗi đôi khi **không ném exception**, mà âm thầm tính toán sai:

```java
// Đoạn minh họa trong lớp con:
private int retryLimit = 3;
private boolean enabled = true;

@Override
protected void printStatus() {
    System.out.println("retryLimit=" + retryLimit
            + ", enabled=" + enabled);
}
```

Nếu được gọi quá sớm, override sẽ nhìn thấy `retryLimit=0, enabled=false`. Vì `0` và `false` là giá trị hợp lệ về mặt kiểu dữ liệu, lỗi có thể len vào quyết định nghiệp vụ hoặc bị ghi lại thành dữ liệu sai mà không báo lỗi ngay.

### 4.3. Khi lời gọi sớm đồng thời làm `this` thoát ra

Nếu override được gọi từ constructor rồi đăng ký `this` với listener hoặc registry, hoặc lên lịch tác vụ giữ tham chiếu đối tượng, mã khác có thể sử dụng đối tượng trước khi khởi tạo xong. Tuy nhiên, **dispatch sớm không tự động có nghĩa là tham chiếu đã bị công bố**. Cần kiểm tra hai cơ chế riêng: phương thức nào chạy quá sớm và đối tượng có thoát khỏi constructor hay không.

Bài “Tránh để this thoát ra khi đối tượng chưa khởi tạo xong” tập trung riêng vào callback, thread, safe publication và quan hệ happens-before.

## 5. Những cách gọi gián tiếp thường bị bỏ sót

Chỉ tìm câu lệnh `overridableMethod();` trong constructor là chưa đủ. Cần xem **toàn bộ chuỗi lời gọi xuất phát từ constructor**.

| Dạng code trong constructor | Vì sao cần kiểm tra |
| --- | --- |
| `initialize();`, trong đó `initialize()` lại gọi `hook()` | Constructor không gọi `hook()` trực tiếp nhưng vẫn dẫn tới override. |
| `setValue(x);` với setter không `final` | Lớp con có thể override setter và đọc trạng thái chưa hoàn chỉnh. |
| `System.out.println(this);` hoặc `"obj=" + this` | Chuyển đối tượng thành chuỗi có thể gọi `toString()` đã bị override. |
| `Objects.toString(this)`, logging object, debugger display | Những thao tác tưởng như chỉ để quan sát có thể gọi `toString()`. |
| `registerListener(this)` | Đối tượng có thể được callback gọi lại khi constructor vẫn đang chạy. |
| `executor.execute(() -> useFields())` hoặc tạo thread dùng `this` | Tác vụ bất đồng bộ có thể chạy sớm và đọc trạng thái chưa khởi tạo. |

Một số chi tiết cần phân biệt:

- Gọi `super.method()` từ lớp con chọn phần triển khai ở lớp cha đối với **lời gọi cụ thể đó**, nhưng method lớp cha vẫn có thể tiếp tục gọi một hook ảo khác. `super` không bảo đảm cả chuỗi lời gọi không có dispatch.
- `private` method không bị override; `final` instance method không bị override; `static` method không dispatch như instance method (trùng tên có thể là *hiding*). Nhưng **một phương thức `private` hoặc `final` vẫn có thể gọi phương thức overridable**, nên phải kiểm tra lời gọi bên trong.
- `getClass()` và kiểu thực tế của `this` đã là kiểu lớp con khi chạy trong constructor lớp cha. Không nên suy luận rằng đối tượng “đang là lớp cha” trong giai đoạn ấy.
- Một phương thức được gọi từ constructor còn có thể truy cập trạng thái của lớp con **qua method reference, lambda, callback hoặc listener**. Nguy cơ đến từ thời điểm thực thi và truy cập đối tượng, không đơn thuần từ cách viết cú pháp.

## 6. Các cách thiết kế an toàn hơn

### Cách A — Constructor tự hoàn tất dữ liệu của lớp mình

Constructor lớp cha nên thực hiện các công việc có thể quyết định hoàn toàn từ tham số và trường đã khởi tạo của chính lớp cha: kiểm tra tham số, gán trường, thiết lập bất biến, hoặc gọi helper `private`/`final` được kiểm soát cẩn thận.

Ví dụ:

```java
// Đoạn minh họa về constructor chỉ xử lý trạng thái nội bộ.
abstract class ConnectionBase {
    private final String endpoint;

    protected ConnectionBase(String endpoint) {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("endpoint bắt buộc");
        }
        this.endpoint = endpoint;
    }

    protected final String endpoint() {
        return endpoint;
    }
}
```

Không cần hỏi lớp con xem `endpoint` đã hợp lệ chưa thông qua một hook có thể override. Nếu dữ liệu là tham số constructor, kiểm tra trực tiếp ở nơi nhận dữ liệu thường đơn giản và an toàn hơn.

### Cách B — Tách phần mở rộng sang phương thức được gọi sau `new`

Mẫu Template Method có thể duy trì một quy trình mở rộng rõ ràng, nhưng phương thức khuôn phải được gọi sau khi constructor của lớp con đã chạy xong:

```java
// Đoạn minh họa; các lớp cụ thể sẽ cung cấp executeStep().
abstract class Job {
    public final void run() {
        checkInputs();
        executeStep();
    }

    private void checkInputs() {
        System.out.println("Đã kiểm tra");
    }

    protected abstract void executeStep();
}
```

Luồng sử dụng đúng là tạo một `Job` cụ thể **xong rồi** gọi `run()`. Không gọi `run()` trong constructor `Job`, bởi nó vẫn dẫn tới `executeStep()` đa hình. Nếu có nhiều phương thức gọi gián tiếp, điểm gọi công khai sau khởi tạo vẫn là ranh giới thiết kế dễ kiểm soát hơn.

### Cách C — Cần bước khởi động bắt buộc: dùng factory với hậu khởi tạo rõ ràng

Khi ứng dụng yêu cầu khởi động đối tượng ngay lúc tạo, có thể đặt một phương thức factory kiểm soát thứ tự: tạo đối tượng hoàn chỉnh rồi mới gọi bước khởi động.

```java
// Đoạn minh họa độc lập về ý tưởng factory, không phụ thuộc ví dụ Main.
final class Session {
    private final String user;
    private boolean started;

    private Session(String user) {
        this.user = java.util.Objects.requireNonNull(user);
    }

    public static Session open(String user) {
        Session session = new Session(user);
        session.startInternal();
        return session;
    }

    private void startInternal() {
        started = true;
    }

    public String status() {
        return user + ":" + (started ? "started" : "new");
    }
}
```

Với lớp được thiết kế để kế thừa, factory cũng có thể tạo xong một instance cụ thể rồi gọi hook cần thiết sau khi constructor trả về. Phải kiểm soát việc công bố tham chiếu và đường khởi tạo: nếu đối tượng đã bị lộ cho mã khác **trước** bước hậu khởi tạo, factory chưa giải quyết hoàn toàn vấn đề. Nếu việc khởi động có thể thất bại, cần quy định rõ liệu đối tượng bị lỗi có được trả ra hay phải được dọn dẹp.

### Cách D — Dùng composition nếu đa hình trong lúc khởi tạo không cần thiết

Thay vì để constructor lớp cha dựa trên một method override của lớp con, truyền một dependency đã sẵn sàng qua constructor hoặc chuyển logic biến thiên sang một đối tượng cộng tác. Khi có thể kiểm tra và cung cấp dependency từ bên ngoài, mã khởi tạo không cần dispatch trên `this` chưa hoàn thiện.

Chú ý: dependency được truyền vào cũng có thể gọi callback ngược đến `this` nếu constructor cung cấp tham chiếu ấy. Composition giúp thu hẹp rủi ro thiết kế, nhưng không tự xóa mọi lỗi nếu vẫn để `this` thoát ra quá sớm.

## 7. Một số hiểu lầm cần tránh

**“Constructor không được override, nên không thể gọi override bên trong.”** Đúng là constructor không tham gia override, nhưng **phương thức instance được constructor gọi** vẫn có thể là virtual method và được phân phối động.

**“Lớp con đã khai báo initializer nên trường chắc chắn có giá trị.”** Sai. Initializer trường lớp con chỉ chạy ở bước khởi tạo lớp con, sau khi constructor lớp cha trả về.

**“Đổi trường thành `final` là đủ.”** Sai. `final` trên trường ngăn gán lại sau khi được khởi tạo (theo các quy tắc gán của Java); nó không làm bước gán trường lớp con chạy sớm hơn. Override ở constructor lớp cha vẫn có thể thấy giá trị mặc định.

**“Đổi constructor sang `private` hoặc đổi method khung sang `final` là xong.”** Phải xét đúng nơi dispatch: `private` helper không thể bị override, nhưng helper ấy có thể gọi một hook ảo. `final` trên method khung chỉ ngăn override khung; nếu khung gọi method khác có thể override, nguy cơ còn nguyên.

**“Lỗi này chỉ xảy ra với abstract method.”** Không. Bất kỳ **instance method có thể override** nào gọi từ constructor (kể cả method cụ thể ở base class hoặc `toString()`) đều có thể chọn bản ghi đè ở lớp con.

**“Thấy `null` chứng tỏ Java chưa cấp phát đối tượng con.”** Sai. Toàn bộ đối tượng đã được cấp phát với các giá trị mặc định; phần khởi tạo riêng của lớp con mới là thứ chưa thực thi.

**“Tôi phải thêm `super.printStatus()` trong override để sửa.”** Không đáng tin cậy. Vấn đề là **thời điểm gọi**; gọi thêm phương thức lớp cha không bảo đảm trạng thái lớp con đã sẵn sàng. Cần thay đổi điểm thực thi hoặc thiết kế quan hệ khởi tạo.

## 8. Checklist rà soát code và kiểm thử

Khi review một abstract class hoặc bất kỳ class nào được phép kế thừa:

1. **Đọc các constructor và chuỗi `this(...)`/`super(...)`**. Ghi lại mọi phương thức instance được gọi, kể cả qua helper.
2. **Phân loại từng method được gọi:** `private`, `final`, `static` hay overridable? Với helper `private`/`final`, tiếp tục xem bên trong có gọi hook hoặc publish `this` không.
3. **Xem các override ở lớp con:** chúng đọc trường nào và trường ấy được gán lúc nào? Phân biệt giá trị mặc định với giá trị do field initializer hoặc constructor gán.
4. **Tìm đường thoát của `this`:** callback, listener, đăng ký vào registry, executor, lambda hay khởi động thread.
5. **Chuyển việc cần đa hình sang pha sau khởi tạo**, hoặc gom vào dữ liệu đầu vào constructor và helper chỉ thao tác trạng thái đã có.
6. **Thử các trạng thái khiến lỗi lộ rõ:** trường tham chiếu `null`, trường số bằng `0`, boolean `false`, constructor có nhiều cấp kế thừa. Xác minh cả trường hợp không có exception nhưng đầu ra sai.
7. **Xác minh thứ tự bằng chương trình nhỏ** như ví dụ `Main.java`; phân biệt log trong constructor lớp cha, initializer lớp con và logic chạy sau `new`.

Nếu dùng công cụ phân tích mã nguồn, cảnh báo tương đương “constructor invokes overridable method” là tín hiệu để kiểm tra. Không phải mọi lời gọi đều dẫn tới lỗi nhìn thấy ngay, nhưng khi có lớp con và override trong tương lai, rủi ro vẫn tồn tại; API công khai có khả năng mở rộng càng cần tránh thiết kế này.

## 9. Bài tập tự kiểm tra hiểu biết

**Bài 1.** Giả sử `Base()` gọi `getCount()` và lớp con override `getCount()` để trả về `count`, trong khi `count` được khai báo `private int count = 10;`. Khi `Base()` chạy, lời gọi có thể trả về bao nhiêu? **Đáp án: `0`** vì initializer của lớp con chưa chạy; sau khi hoàn thành `new`, giá trị mới là `10`.

**Bài 2.** Thay `getCount()` bằng một helper `private int getCount()` trong chính lớp cha đã đủ loại bỏ dispatch vào override của lớp con chưa? **Có, đối với chính lời gọi helper đó**, vì `private` method không override được. Nhưng vẫn phải kiểm tra helper có gọi phương thức overridable hoặc làm lộ `this` hay không.

**Bài 3.** Nếu lớp cha có phương thức `public final void initialize()`, bên trong gọi `configure()` là `protected abstract`, liệu có an toàn để gọi `initialize()` trong constructor lớp cha không? **Không.** `initialize()` tuy `final` vẫn thực thi `configure()` đa hình. Đưa lời gọi `initialize()` ra sau khi `new` hoàn thành.

**Bài 4.** Có nên cấm tất cả phương thức instance trong constructor không? **Không cần.** Constructor có thể gọi helper không overridable, làm việc với trạng thái đã khởi tạo, không làm lộ `this`. Quy tắc cần tránh là gọi vào logic có thể truy cập phần lớp con chưa sẵn sàng hoặc tạo cơ hội cho mã bên ngoài nhìn thấy đối tượng chưa hoàn chỉnh.

## 10. Ghi nhớ

- Constructor lớp cha được thực thi trước phần khởi tạo riêng của lớp con, nhưng **dynamic dispatch đã hoạt động theo kiểu thực tế của đối tượng** ngay khi constructor lớp cha chạy.
- Trường lớp con chưa khởi tạo có thể được quan sát qua override: **`null`, `0`, `false`** thay vì giá trị mà lập trình viên mong đợi.
- Gọi **trực tiếp hoặc gián tiếp** phương thức overridable từ constructor đều có thể nguy hiểm; `abstract`, `toString()`, setter và hook trong một method `final` đều cần kiểm tra.
- Giữ constructor tập trung vào trạng thái do chính nó kiểm soát; đưa hook đa hình sang phương thức được gọi **sau khi toàn bộ quá trình `new` hoàn thành**. Không publish `this` quá sớm.
