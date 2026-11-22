# Khởi tạo đệ quy, phụ thuộc vòng và giá trị chưa hoàn thiện trong Java

## 1. Vấn đề: một lớp được dùng khi chính nó còn đang khởi tạo

Một lớp Java có thể đang chạy các biểu thức gán trường `static` hoặc khối `static { ... }` thì lại truy cập đến chính lớp đó — trực tiếp hoặc thông qua một lớp khác. Java cho phép tình huống này trong nhiều trường hợp, nhưng kết quả không phải lúc nào cũng trực giác: **một trường `static` có thể bị đọc khi mới mang giá trị mặc định, trước khi initializer của nó chạy xong**.

Hai hiện tượng cần phân biệt ngay:

1. **Đệ quy khởi tạo trên cùng một thread:** đang khởi tạo lớp A, mã gọi đến A lần nữa (có thể theo vòng A → B → A). JVM nhận ra cùng thread đã khởi tạo A dở dang và **không chạy lại** bộ khởi tạo của A; lần yêu cầu đệ quy được coi là hoàn tất cho luồng đó. Mã có thể đọc những trường A chưa được gán giá trị cuối cùng.
2. **Vòng phụ thuộc khởi tạo giữa nhiều thread:** thread T1 đang khởi tạo A rồi cần B, trong khi T2 đang khởi tạo B rồi cần A. Mỗi thread có thể phải chờ thread kia hoàn tất và tạo thành **deadlock**.

Hai trường hợp đều bắt nguồn từ vòng phụ thuộc nhưng cơ chế và triệu chứng khác nhau. **Một vòng A → B → A trên cùng thread không tự động gây StackOverflowError hoặc deadlock.** Nó thường tạo kết quả “lạ” do thấy trạng thái chưa hoàn thiện. Vòng xuyên thread có thể chặn nhau mãi mà không ném exception.

## 2. Các giai đoạn liên quan đến giá trị của trường `static`

Trước khi phân tích vòng phụ thuộc, cần xác định thời điểm JVM tạo giá trị:

```text
Loading
   ↓
Linking
   ├── Verification
   ├── Preparation: cấp phát/đặt giá trị mặc định cho static fields
   └── Resolution: có thể thực hiện sớm hoặc trì hoãn
   ↓
Initialization
   ├── đảm bảo các lớp cha cần thiết đã được khởi tạo
   ├── chạy các static field initializers theo thứ tự khai báo
   └── chạy các static blocks theo thứ tự tương ứng
   ↓
Initialized successfully
```

**Preparation** chuẩn bị trường `static` bằng giá trị mặc định: số nguyên `0`, `boolean=false`, tham chiếu `null`, v.v. **Initialization** thực hiện các câu lệnh/biểu thức gán trong mã nguồn, theo thứ tự văn bản của trường và static block. Vì vậy, với:

```java
static int count = calculate();
static String label = "ready";
```

trong lúc `calculate()` chưa trả về, `count` và `label` có thể vẫn là `0` và `null` đối với mã đang khởi tạo đệ quy trên **cùng thread**.

Có ngoại lệ về **constant variables** được biểu diễn bằng thuộc tính `ConstantValue`: JLS quy định chúng được gán trong thủ tục khởi tạo trước khi chạy các initializer thông thường, và bên sử dụng có thể đã inline hằng lúc biên dịch. Do đó không suy diễn mọi `static final` đều quan sát được giá trị mặc định; chỉ các trường `static` **không phải compile-time constant** là trường hợp cần đặc biệt lưu ý ở bài này.

Đừng đồng nhất *đã load*, *đã link* với *đã initialize*. Các lần đọc `Class<?>` hoặc `T.class` không tự kích hoạt việc chạy bộ khởi tạo của T; còn việc đọc trường static không phải hằng thời gian biên dịch thường yêu cầu khởi tạo lớp **khai báo** trường đó.

## 3. JVM xử lý yêu cầu khởi tạo đệ quy như thế nào?

Theo quy trình tại **JLS `12.4.2**, mỗi lớp hoặc interface runtime có một trạng thái khởi tạo, có thể mô tả khái quát:

| Trạng thái | Ý nghĩa khi một thread yêu cầu initialize |
|---|---|
| Chưa khởi tạo | Thread bắt đầu thủ tục khởi tạo nếu được chọn để làm việc đó |
| Đang được thread **khác** khởi tạo | Thread yêu cầu phải chờ và kiểm tra lại sau khi trạng thái đổi |
| Đang được **chính thread hiện tại** khởi tạo | Yêu cầu đệ quy hoàn tất bình thường; không chạy lại `<clinit>` |
| Đã khởi tạo thành công | Dùng ngay, không chạy lại `<clinit>` |
| Ở trạng thái lỗi (erroneous) | Tiếp tục sử dụng theo đường kích hoạt init sẽ thất bại, thường với `NoClassDefFoundError` |

JVM có cơ chế đồng bộ hóa khởi tạo riêng cho từng **runtime class/interface**. Không cần và không nên cố tự quản lý “init lock” qua `synchronized (SomeClass.class)` để kiểm soát chu trình khởi tạo. Việc JVM triển khai khóa khởi tạo không nhất thiết tương đương Java monitor mà mã ứng dụng dùng.

Với trường hợp đệ quy **cùng thread**, chuỗi được hình dung như sau:

```text
Thread T:
  initialize A
      A.<clinit> bắt đầu
          đọc B.value
              initialize B
                  B.<clinit> bắt đầu
                      đọc A.value
                          A đang init bởi T
                          → yêu cầu đệ quy được coi đã xử lý
                          → trả về giá trị hiện có của A.value
                  B.<clinit> hoàn tất
          A.<clinit> hoàn tất
  A đã khởi tạo thành công
```

Điều cốt lõi: **“yêu cầu khởi tạo đệ quy hoàn tất” không có nghĩa `A.<clinit>` đã chạy xong**. Nó chỉ giúp cùng thread tiếp tục mà không khởi tạo A vô hạn. Trạng thái trường A vẫn phản ánh những gì đã được gán **tới thời điểm truy cập**.

## 4. Ví dụ đầy đủ: vòng A → B → A và giá trị còn mặc định

Tạo file `CircularInitDemo.java`:

```java
public class CircularInitDemo {
    static class A {
        static int value = compute();

        static int compute() {
            System.out.println("A computes using B");
            return B.value + 1;
        }

        static {
            System.out.println("A finalized value=" + value);
        }
    }

    static class B {
        static int value = compute();

        static int compute() {
            System.out.println("B computes using A");
            return A.value + 10;
        }

        static {
            System.out.println("B finalized value=" + value);
        }
    }

    public static void main(String[] args) {
        boolean bFirst = args.length > 0 && args[0].equals("B");
        System.out.println("Start: " + (bFirst ? "B" : "A"));

        if (bFirst) {
            System.out.println("B.value=" + B.value);
            System.out.println("A.value=" + A.value);
        } else {
            System.out.println("A.value=" + A.value);
            System.out.println("B.value=" + B.value);
        }
    }
}
```

Biên dịch một lần bằng Java 17+:

```bash
javac CircularInitDemo.java
```

### 4.1. Truy cập A trước

```bash
java CircularInitDemo
```

Stdout chính xác:

```text
Start: A
A computes using B
B computes using A
B finalized value=10
A finalized value=11
A.value=11
B.value=10
```

Phân tích từng bước:

1. Đọc `A.value` trong `main` buộc JVM khởi tạo A. Trước khi các phép gán chạy, cả `A.value` và `B.value` đều có giá trị mặc định `0` khi lớp tương ứng đã được chuẩn bị.
2. `A.compute()` in dòng đầu, rồi yêu cầu `B.value`; vì B chưa khởi tạo, cùng thread bắt đầu khởi tạo B.
3. `B.compute()` in dòng thứ hai, rồi yêu cầu `A.value`. A **đang** khởi tạo bởi chính thread đó, nên JVM cho phép yêu cầu đệ quy hoàn tất mà không chạy lại initializer của A. **Phép gán cho `A.value` vẫn chưa xong**, nên B đọc được `0`.
4. B tính `0 + 10 = 10`, gán vào `B.value`, rồi chạy static block in `B finalized value=10`.
5. Trở lại A: `B.value` giờ là `10`; A tính `10 + 1 = 11`, gán vào `A.value` rồi in `A finalized value=11`.
6. `main` nhận `A.value=11`, sau đó đọc `B.value=10`; các lớp đã khởi tạo nên không chạy initializer lần nữa.

**Kết luận của ví dụ:** JVM không “đợi cho đủ dữ liệu” khi chính thread đang chạy initializer lại đọc một trường chưa gán. Nó trả giá trị hiện có, ở đây là `0`.

### 4.2. Truy cập B trước

Chạy chương trình ở **một JVM mới** với tham số `B`:

```bash
java CircularInitDemo B
```

Stdout chính xác:

```text
Start: B
B computes using A
A computes using B
A finalized value=1
B finalized value=11
B.value=11
A.value=1
```

Lần này B khởi tạo trước và bị đọc ngược khi chưa gán, nên `B.value=0` trong lúc tính A. Sau đó `A.value=1` và `B.value=11`. **Cùng source code nhưng điểm truy cập đầu tiên khác nhau dẫn đến trạng thái cuối khác nhau.**

Hai lần chạy phải ở **hai tiến trình JVM riêng biệt**, vì trong cùng JVM đã khởi tạo thành công A/B thì đổi thứ tự đọc sau đó **không khởi tạo lại** lớp. Đây là một lỗi thường gặp khi viết test thực nghiệm về class initialization.

## 5. Đệ quy trong chính một lớp: không nhất thiết có hai lớp

Vòng phụ thuộc cũng xuất hiện khi static initializer của lớp gọi một static method của chính lớp đó, và method đọc một trường chưa được gán.

Tạo `SelfInitDemo.java`:

```java
public class SelfInitDemo {
    static class Settings {
        static int first = computeFirst();
        static int second = 8;

        static int computeFirst() {
            System.out.println("computeFirst sees second=" + second);
            return second + 1;
        }

        static {
            System.out.println(
                    "static block sees first=" + first
                    + ", second=" + second
            );
        }
    }

    public static void main(String[] args) {
        System.out.println("first=" + Settings.first);
        System.out.println("second=" + Settings.second);
    }
}
```

Lệnh chạy:

```bash
javac SelfInitDemo.java
java SelfInitDemo
```

Stdout:

```text
computeFirst sees second=0
static block sees first=1, second=8
first=1
second=8
```

`Settings.second` chưa được phép gán `8` khi `computeFirst()` chạy, nên ở thời điểm đó vẫn là `0`. Java có quy tắc hạn chế một số tham chiếu trực tiếp đến static field khai báo phía sau trong initializer (**illegal forward reference**), nhưng việc đọc qua một method như ví dụ vẫn biên dịch hợp lệ. Quy tắc compiler này không bảo đảm rằng mọi lần quan sát trường static đều đã hoàn thiện.

Hãy tránh dùng kết quả từ field khai báo phía sau làm điều kiện hợp lệ ngay trong field initializer nằm phía trước nếu logic phụ thuộc giá trị sau khởi tạo.

## 6. Vòng phụ thuộc có thể để lại `null` hoặc object chưa sẵn sàng

Với field kiểu tham chiếu, giá trị mặc định là **`null`**. Điều này nguy hiểm hơn phép cộng với `0`: code có thể ném `NullPointerException`, lưu `null` vào cache hoặc truyền một tham chiếu không hợp lệ ra ngoài.

### 6.1. Ví dụ `static final` không bảo vệ được vòng khởi tạo

Tạo `CircularReferenceDemo.java`:

```java
public class CircularReferenceDemo {
    static final class Holder {
        final String name;

        Holder(String name) {
            this.name = name;
        }
    }

    static final class Left {
        static final Holder HOLDER = Right.HOLDER;

        static {
            System.out.println("Left.HOLDER=" + Left.HOLDER);
        }
    }

    static final class Right {
        static final Holder HOLDER = Left.HOLDER;

        static {
            System.out.println("Right.HOLDER=" + Right.HOLDER);
        }
    }

    public static void main(String[] args) {
        System.out.println("read Left");
        System.out.println("result Left=" + Left.HOLDER);
        System.out.println("result Right=" + Right.HOLDER);
    }
}
```

Chạy:

```bash
javac CircularReferenceDemo.java
java CircularReferenceDemo
```

Stdout:

```text
read Left
Right.HOLDER=null
Left.HOLDER=null
result Left=null
result Right=null
```

Đọc `Left.HOLDER` khiến JVM khởi tạo Left, bắt đầu đánh giá `Right.HOLDER`. Bên trong khởi tạo Right, việc đọc `Left.HOLDER` thuộc **cùng thread đang khởi tạo Left**, và phép gán của Left chưa kết thúc, nên giá trị là `null`. Right giữ `null`, sau đó Left cũng giữ `null`.

Cả hai field đều khai báo `static final`, nhưng `Holder` là kiểu tham chiếu không phải `String` compile-time constant; `final` chỉ ràng buộc việc gán field, **không bảo đảm đồ thị khởi tạo phụ thuộc vòng sẽ tự tạo giá trị hợp lệ**. Trong ví dụ, constructor của `Holder` thậm chí chưa được gọi lần nào. `final` cũng không biến một tham chiếu `null` thành object hợp lệ.

### 6.2. Phân biệt “giá trị chưa hoàn thiện” với “object chưa xây dựng xong”

Có ít nhất ba kiểu vấn đề:

- **Static field còn mặc định:** chưa được gán, thread đệ quy thấy `0`/`false`/`null`.
- **Static field đã được gán tạm nhưng sẽ còn thay đổi:** logic giữa các static blocks có thể đọc được giá trị trung gian.
- **Object bị công bố quá sớm:** static initializer/constructor đưa `this` hoặc object đang xây dựng vào registry/callback; một đoạn mã khác có thể sử dụng object trước khi các invariant của nó được thiết lập. Đây còn liên quan an toàn công bố (safe publication), đặc biệt giữa nhiều thread, và không thể chỉ giải thích bằng mặc định của static field.

Không kết luận rằng mọi field sẽ luôn là giá trị mặc định trong vòng phụ thuộc: **thứ tự gán đã thực hiện** mới quyết định giá trị quan sát. Field đã gán từ trước có thể hoàn toàn hợp lệ; field chưa gán thì có thể chưa hợp lệ.

## 7. Hằng biên dịch khi truy vết vòng initialization

`static final int LIMIT = 10` và `static final String LABEL = "ready"` có thể được compiler inline, nên phép đọc không nhất thiết đi vào vòng initialization. `static final Object TOKEN = new Object()` và `static final int X = parse()` phải được gán lúc runtime, vì vậy có thể bị đọc dở dang nếu initializer tạo vòng. Bài về **hằng biên dịch** định nghĩa đầy đủ constant variable; ở đây hãy vẽ cạnh dependency chỉ cho thao tác thực sự cần initialization.

## 8. Vòng giữa hai thread: vì sao có thể deadlock?

Xét hai lớp mà bộ khởi tạo lần lượt cần class kia:

```text
Thread T1                              Thread T2
---------                              ---------
bắt đầu initialize A                  bắt đầu initialize B
A.<clinit> ...                         B.<clinit> ...
muốn đọc B.value                      muốn đọc A.value
B đang initialize bởi T2             A đang initialize bởi T1
→ T1 phải chờ T2                       → T2 phải chờ T1
              \                        /
               Vòng chờ (deadlock)
```

Đây là một **lịch thực thi có thể xảy ra**, không phải kết cục bắt buộc của mọi chương trình chứa vòng A ↔ B. Nếu chỉ một thread chủ động khởi tạo cả A và B trước khi thread kia vào cuộc, nó có thể gặp hiện tượng giá trị mặc định kiểu mục 4 mà **không deadlock**. Scheduler, thời điểm khởi tạo và việc thư viện vô tình chạm tới class trước đó đều ảnh hưởng hiện tượng quan sát.

Một **deadlock khác** có thể xảy ra ngay cả khi không có static field A ↔ B:

```text
Thread T1 khởi tạo ClassA
  └─ trong ClassA.<clinit>:
       tạo Thread T2
       gọi T2.join() để chờ T2
                         Thread T2:
                           gọi ClassA.someStaticMethod()
                           → cần chờ T1 khởi tạo ClassA xong
T1 đợi T2, T2 đợi T1 ⇒ deadlock
```

**Tránh chờ vô thời hạn bên trong static initializer**, chẳng hạn `Thread.join()` không timeout, chờ `Future.get()` trên task phụ thuộc lớp đang init, hoặc chờ một executor/service được khởi động theo chính đường phụ thuộc đó.

### 8.1. Vì sao deadlock không giống vòng khởi tạo đệ quy cùng thread?

Khi cùng thread đang khởi tạo A mà lại yêu cầu A, JVM có quy tắc **đệ quy cùng thread** để kết thúc yêu cầu lồng nhau; trường có thể còn mặc định. Khi **thread khác** yêu cầu A, JVM phải bảo toàn việc A chỉ được khởi tạo một lần và thread thứ hai phải chờ trạng thái của A. Điều đó bảo vệ tính nhất quán sau initialization nhưng khiến đồ thị chờ vòng có thể bị kẹt.

Cơ chế này thuộc initialization của JVM; `ThreadMXBean.findDeadlockedThreads()` chủ yếu phát hiện vòng chờ trên monitor/ownable synchronizer và **không bảo đảm tìm ra mọi class-initialization deadlock**. Hãy xem toàn bộ thread dump và những class đang khởi tạo thay vì chỉ dựa vào một API deadlock detector trả về `null`.

## 9. Điều gì được bảo đảm giữa các thread?

Java cần có ngữ nghĩa đồng bộ cho initialization: sau khi class đã **khởi tạo thành công**, các thread sử dụng nó qua những hành động yêu cầu init có thể tiếp tục với các hiệu ứng của initialization đã được công bố theo quy tắc happens-before tương ứng. JVM có thể tối ưu cơ chế khóa nhưng phải giữ hệ quả đồng bộ mà JLS yêu cầu.

Điều này **không** đồng nghĩa:

- Một thread khác có thể tùy tiện đọc field thông qua `getstatic` trong khi class đang do thread đầu tiên khởi tạo: JVM phải áp dụng quy tắc chờ init khi thích hợp.
- Việc object được tạo và chia sẻ qua một registry/callback từ giữa `<clinit>` sẽ luôn an toàn: nếu object thoát ra trước khi hoàn thành constructor hoặc không được công bố đúng cách, đó là vấn đề về trạng thái object và Java Memory Model.
- Các giá trị mutable `static` được sửa **sau khi khởi tạo** tự động thread-safe: vẫn cần đồng bộ thích hợp, `volatile`, immutable objects hoặc concurrent collections tùy trường hợp.

**Trạng thái chưa hoàn thiện trong bài này** thường xuất hiện rất rõ khi **chính thread khởi tạo** đọc ngược các trường còn mặc định. Không dùng hiện tượng này để kết luận rằng Java cho phép mọi thread khác thấy trạng thái đang khởi tạo của lớp.

## 10. Đồ thị dependency JVM và dependency do ứng dụng

Initialize `Child` đòi hỏi initialize `Parent` trước, tức có cạnh bắt buộc **Child → Parent**. Nếu initializer của `Parent` tự truy cập static member của `Child`, ứng dụng tạo thêm cạnh **Parent → Child** và có thể thành vòng. Khi debug, ghi riêng cạnh từ thuật toán JVM với cạnh do `getstatic`/`invokestatic` trong code.

## 11. Kết quả cần phòng tránh

Phụ thuộc vòng có thể lưu `0`/`null` vào registry/cache, gây `NullPointerException` hoặc tạo kết quả khác nhau theo lớp được active use đầu tiên. Lỗi chưa xử lý còn có thể làm class erroneous, dẫn đến `ExceptionInInitializerError` ở lượt đầu và `NoClassDefFoundError` ở lượt sau. **Không phải mọi vòng đều ném lỗi**: `CircularInitDemo` chứng minh kết quả số khác nhau dù cả hai lượt initialization hoàn tất bình thường.

Bài cuối chương phân tích xử lý erroneous class và class loader; ở đây ưu tiên tìm và phá vòng dependency trước khi field dở dang bị sử dụng.

## 12. Cách thiết kế để tránh vòng phụ thuộc initialization

### 12.1. Xác định đồ thị phụ thuộc và phá vòng

Vẽ cạnh `A → B` khi **initializer của A** phải chạm vào thành viên không hằng của B hoặc gọi hành động khiến B phải khởi tạo:

```text
Thiết kế nguy hiểm:

A.<clinit> ──needs──> B.value
     ▲                    │
     └────needs───────────┘

Thiết kế tốt hơn:

main / Bootstrap
       ├──create──> ServiceA
       ├──create──> ServiceB
       └──wire────> quan hệ phụ thuộc rõ ràng
```

Một dependency DAG (không có chu trình) dễ kiểm soát hơn các static initializer gọi lẫn nhau. Nếu A và B phải tham chiếu hai chiều, có thể tạo object trước, rồi **wire các tham chiếu trong một bước khởi động có kiểm soát** thay vì để field initializer quyết định thứ tự theo lần chạm class đầu.

### 12.2. Chuyển initialization phức tạp sang điểm khởi động rõ ràng

Ví dụ dưới đây loại bỏ việc A và B tự tìm nhau trong static initializer.

Tạo `ExplicitBootstrapDemo.java`:

```java
public class ExplicitBootstrapDemo {
    static final class ServiceA {
        private ServiceB peer;

        void connect(ServiceB peer) {
            this.peer = peer;
        }

        String readPeer() {
            return peer.name();
        }

        String name() {
            return "A";
        }
    }

    static final class ServiceB {
        private ServiceA peer;

        void connect(ServiceA peer) {
            this.peer = peer;
        }

        String readPeer() {
            return peer.name();
        }

        String name() {
            return "B";
        }
    }

    public static void main(String[] args) {
        ServiceA a = new ServiceA();
        ServiceB b = new ServiceB();
        a.connect(b);
        b.connect(a);

        System.out.println("A sees " + a.readPeer());
        System.out.println("B sees " + b.readPeer());
    }
}
```

Chạy:

```bash
javac ExplicitBootstrapDemo.java
java ExplicitBootstrapDemo
```

Stdout:

```text
A sees B
B sees A
```

Ở đây graph tham chiếu đối tượng vẫn hai chiều, nhưng quá trình **xây dựng và kết nối** diễn ra theo thứ tự rõ ràng. Mã chỉ gọi `readPeer()` sau khi đã kết nối cả hai. Nếu chia sẻ cho các thread khác, tiếp tục cần cơ chế công bố/synchronization phù hợp; ví dụ trên chỉ có một thread.

### 12.3. Lazy initialization cần được dùng đúng

Một initialization-on-demand holder thường có dạng:

```java
public final class ServiceRegistry {
    private ServiceRegistry() {}

    private static final class Holder {
        private static final ServiceRegistry INSTANCE =
                new ServiceRegistry();
    }

    public static ServiceRegistry getInstance() {
        return Holder.INSTANCE;
    }
}
```

Đây là mẫu class **minh họa độc lập**, không có `main`; nếu muốn thử, gọi `ServiceRegistry.getInstance()` từ chương trình khác. Holder tách thời điểm khởi tạo singleton khỏi thời điểm load class ngoài và hưởng bảo đảm initialization an toàn của JVM.

**Nhưng lazy holder không tự giải quyết vòng phụ thuộc:** nếu constructor `ServiceRegistry()` gọi sang một holder khác rồi holder đó lại gọi `ServiceRegistry.getInstance()` trước khi `Holder.INSTANCE` được gán, vẫn có thể quan sát `null` hoặc gặp lỗi/deadlock. Cần bảo đảm graph xây dựng thực sự không có vòng yêu cầu instance chưa hoàn tất.

### 12.4. Những nguyên tắc thực hành

- Giữ initializer `static` đơn giản, hữu hạn, độc lập và ít side effect; ưu tiên các giá trị bất biến khởi tạo từ dữ liệu có sẵn.
- Không gọi qua lại giữa các singleton đang xây dựng; tách **allocate**, **configure**, **publish** nếu các object phụ thuộc hai chiều.
- Tránh tạo thread, đợi network, `join` hay chờ Future trong `<clinit>`; các điểm chờ có thể gọi ngược về class đang init.
- Không công bố `this` từ constructor tới global registry/callback trước khi invariant của object hoàn tất.
- Kiểm thử startup trong **JVM mới** với những đường kích hoạt đầu tiên khác nhau khi nghi ngờ phụ thuộc thứ tự.
- Kiểm tra xem trình biên dịch có inline một hằng không; đừng nhầm việc đọc hằng `static final` với active use tạo initialization.
- Với code được chạy qua ClassLoader tùy chỉnh/plugin, xác định chính xác **defining loader** của mỗi class: cùng binary name do các loaders khác nhau định nghĩa sẽ có các trạng thái khởi tạo độc lập.

## 13. Quy trình debug vòng khởi tạo và deadlock

1. **Tìm lần dùng đầu:** truy cập nào kích hoạt `getstatic`, `putstatic`, `invokestatic`, `new` hoặc reflection có yêu cầu initialization? Chú ý đến class *khai báo* field/method.
2. **Đọc static initializers theo thứ tự văn bản**, gồm biểu thức gán field và khối `static`; hàm helper được gọi từ đó là một phần của đồ thị phụ thuộc.
3. **Ghi đồ thị A → B → A**: cạnh nào do static initializer, cạnh nào do superclass initialization hoặc hoạt động gọi ngược?
4. **Phân biệt lịch sử thread:** nếu chu trình trên cùng thread, kiểm tra field chưa được gán; nếu nhiều thread, tìm thread đang init mỗi class và đang đợi nhau.
5. **Dùng trace có chủ đích:** đặt log trước/sau biểu thức quan trọng, kèm thread name; tránh tạo log có side effect khởi tạo class khác. Log lớp được **load** không chứng minh lớp đã **initialized**.
6. **Xem thread dump khi bị treo:** dùng `jcmd <pid> Thread.print -l` hoặc `jstack <pid>` nếu JDK hỗ trợ; đối chiếu stack đang ở `<clinit>`, constructor, `join`, `Future.get` và các wait. Không kết luận không deadlock chỉ vì detector cho monitor không tìm thấy vòng.
7. **Ghi lại exception đầu tiên:** với `ExceptionInInitializerError`, xem `getCause()`; với `NoClassDefFoundError` sau đó, quay lại lỗi initialization trước thay vì chỉ sửa classpath.
8. **Chạy lại trong process mới:** class erroneous không được khởi tạo lại trong cùng runtime class; trạng thái initialized cũng không tự xóa giữa các unit test chạy cùng JVM.
9. **Sửa dependency**, không vá bằng `Thread.sleep()`, thêm `synchronized` ngẫu nhiên hoặc phụ thuộc thời gian chạy; những thao tác đó thường chỉ thay đổi lịch và che lỗi.

Có thể xem bytecode của một nested class, ví dụ từ `CircularInitDemo`:

```bash
javap -c -p 'CircularInitDemo$A'
```

Trên shell Unix hoặc PowerShell, dấu nháy đơn ngăn ký tự `$` bị shell diễn giải. `javap` thường hiển thị phần `static {};` với các lệnh `invokestatic` và `putstatic` tương ứng `A.compute()` và gán `A.value`. Bytecode giúp tìm thứ tự gán, nhưng để chứng minh thread nào đang init lúc lỗi, vẫn cần runtime trace/thread dump.

## 14. Tình huống cần phân biệt

| Tình huống | Có thể xảy ra | Điều không nên kết luận |
|---|---|---|
| A đang init trên T, gọi A lần nữa cũng trên T | Yêu cầu đệ quy hoàn tất, đọc giá trị đang có | `<clinit>` được chạy từ đầu lần hai |
| A → B → A trên một thread | B đọc mặc định của một field A chưa gán | Mọi vòng đều deadlock |
| T1 init A chờ B; T2 init B chờ A | Cross-thread deadlock | JVM nhất thiết ném `StackOverflowError` |
| Một thread khác cần A khi T đang init A | Thread khác chờ init thành công/thất bại theo quy tắc JVM | Luôn được phép thấy field còn mặc định |
| Đọc `static final int X = 5` | Hằng được inline, có thể không kích hoạt init | Mọi `static final` đều hành xử như nhau |
| Static initializer ném unchecked exception | `ExceptionInInitializerError` lần đầu, class erroneous về sau | JVM sẽ tự thử init lại mỗi lần |
| Holder trì hoãn tạo singleton | Có thể giảm eager init | Chắc chắn giải được chu trình constructor/holder |

## 15. Câu hỏi tự kiểm tra

1. **Nếu T đang khởi tạo A và trong `A.<clinit>` mã lại yêu cầu initialize A thì JVM làm gì?** Yêu cầu lồng nhau của cùng T hoàn tất bình thường; `A.<clinit>` không bị chạy lại từ đầu.
2. **Tại sao trong `CircularInitDemo` chạy A trước cho `B.value=10`, chạy B trước lại cho `A.value=1`?** Vì lớp bị đọc ngược trong khi chưa hoàn tất initializer đang có `value=0`, rồi phép tính diễn ra theo thứ tự khác.
3. **Dùng `static final Holder` có ngăn field nhận `null` trong vòng init không?** Không; `Holder` không phải compile-time constant, `final` không loại bỏ việc một field chưa được gán bị đọc đệ quy.
4. **Hai thread cùng yêu cầu init một class chưa init có cùng chạy `<clinit>` không?** Không; JVM điều phối để class init một lần, thread còn lại phải tuân theo trạng thái/đợi.
5. **A → B → A có luôn deadlock không?** Không; cùng một thread thường thấy trạng thái chưa hoàn thiện, còn lịch cross-thread chờ nhau có thể deadlock.
6. **Nếu initializer thất bại, gọi lại static field sẽ tự retry không?** Không; class runtime chuyển sang trạng thái erroneous và lần sử dụng tiếp thất bại.
7. **Holder singleton có chắc tránh vòng không?** Không, nếu constructor/initializer của holder tạo vòng gọi ngược đến instance chưa gán.
8. **Phương án ổn định nhất khi hai service cần tham chiếu hai chiều là gì?** Tách construction/wiring khỏi static initializer; tạo object và kết nối phụ thuộc ở startup rõ ràng, rồi mới publish/sử dụng.

## Tài liệu chuẩn

- [Java Language Specification — 12.4.1, When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.1): tác nhân yêu cầu khởi tạo và trường hợp dùng constant variable.
- [Java Language Specification — 12.4.2, Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.2): trạng thái lớp, thread đang khởi tạo, trường hợp yêu cầu đệ quy và khi khởi tạo thất bại.
- [Java Language Specification — 4.12.4, final Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4): constant variables và phân biệt với `final` thông thường.
- [Java Virtual Machine Specification — 5.5, Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5): cơ chế initialization ở mức JVM.
- [Java Language Specification — 17, Threads and Locks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html): happens-before và đồng bộ giữa thread.

**Điểm phải nắm:** Đệ quy khởi tạo cùng thread có thể đọc **giá trị chưa gán**; vòng khởi tạo giữa nhiều thread có thể tạo **vòng chờ**. Cả hai là dấu hiệu cần thiết kế lại dependency startup để trạng thái quan trọng chỉ được sử dụng khi đã hoàn chỉnh.
