# Điểm can thiệp khi khởi tạo đối tượng và thực thi hàm tạo trong AOP

> **Mục tiêu học tập:** Phân biệt điểm can thiệp tại **nơi yêu cầu tạo đối tượng** với điểm can thiệp **khi hàm tạo được thực thi**; hiểu mối quan hệ giữa các join point này và vòng đời khởi tạo đối tượng; nhận biết phạm vi của pointcut/advice, thứ tự thực thi, xử lý ngoại lệ và các trường hợp không thể chặn bằng một cơ chế AOP nhất định.

## 1. Vì sao quá trình tạo đối tượng cũng có thể là điểm can thiệp?

Khi nói đến AOP (Aspect-Oriented Programming), người học thường hình dung advice chạy trước hoặc sau một phương thức nghiệp vụ. Tuy nhiên, việc tạo đối tượng cũng có những ranh giới thực thi đáng quan sát: chương trình yêu cầu tạo một đối tượng, một constructor được gọi, các bước khởi tạo diễn ra và đối tượng có thể được trả về cho nơi gọi.

Ví dụ một ứng dụng muốn thu thập số lần tạo đối tượng thuộc nhóm cần theo dõi, ghi vết các lần tạo thất bại, đo chi phí khởi tạo hoặc xác minh một chính sách tại ranh giới tạo tài nguyên. Nếu cùng một quy tắc được chèn thủ công vào nhiều nơi viết `new` hoặc nhiều constructor, mã dễ bị phân tán và đan xen với nghiệp vụ. Mô hình AOP cho phép mô tả **join point** liên quan đến những hoạt động này khi cơ chế được dùng có hỗ trợ.

Cần tránh kết luận rằng cứ có `new` là mọi AOP đều chặn được. Tập loại join point và vị trí advice được chạy **phụ thuộc mô hình AOP và kỹ thuật weaving**. Bài học này giải thích ngữ nghĩa chung, có ví dụ Java 17 quan sát vòng đời, và phân biệt rõ mã Java minh họa với weaving thực sự.

## 2. Các thuật ngữ cần tách bạch

- **Đối tượng (object):** một thể hiện của lớp có trạng thái và danh tính riêng, được cấp phát và khởi tạo theo quy tắc ngôn ngữ/runtime.
- **Hàm tạo (constructor):** đơn vị khởi tạo gắn với việc thiết lập một thể hiện mới; trong Java, constructor không có kiểu trả về và không phải một phương thức thông thường.
- **Class instance creation expression:** biểu thức như `new Order(...)` ở **nơi gọi**.
- **Constructor invocation:** hành động yêu cầu chạy một constructor; trong Java còn có lời gọi chuyển tiếp `this(...)` hoặc `super(...)` bên trong constructor.
- **Constructor execution:** quá trình thực hiện logic khởi tạo của một constructor cụ thể.
- **Join point:** vị trí/hoạt động trong mô hình thực thi mà AOP có thể nhận diện và gắn hành vi, nếu được hỗ trợ.
- **Pointcut:** điều kiện lựa chọn tập join point cần can thiệp.
- **Advice:** hành vi bổ sung chạy trước, sau hoặc bao quanh join point theo mô hình tương ứng.
- **Weaving:** cách kết hợp hành vi aspect vào chương trình hoặc luồng thực thi.

**“Khởi tạo đối tượng”** theo nghĩa rộng có thể bao trùm nhiều bước hơn **“chạy thân constructor”**. Tùy ngôn ngữ AOP, các điểm như *constructor call*, *constructor execution* và *object initialization* có thể được coi là những loại join point khác nhau, có phạm vi và thời điểm khác nhau.

## 3. Điểm can thiệp tại nơi gọi hàm tạo: constructor call

Xét Java:

```java
Order order = new Order("A-100");
```

Trong nhiều mô hình AOP, ta có thể quan tâm đến join point **constructor call**: vị trí mã yêu cầu tạo một `Order`. Đó là góc nhìn **từ phía nơi gọi**.

Một pointcut khái niệm có thể mô tả:

```text
Chọn những nơi gọi constructor của Order với đối số định dạng hợp lệ.
```

Nếu cơ chế hỗ trợ advice ở constructor-call join point, chính sách có thể bao quanh thao tác tạo ở một số call site nhất định:

```text
Caller
  |
  |  trước yêu cầu tạo
  v
  new Order(...)
  |
  |  sau khi biểu thức new hoàn tất bình thường
  v
  Caller nhận tham chiếu Order
```

**Những điều cần hiểu:**

1. **Ranh giới call site:** đây là điểm trong luồng của **bên yêu cầu tạo đối tượng**. Nó có thể dùng để đo tổng thời gian của biểu thức tạo đối tượng (tùy cách advice đo và chỗ được chèn).
2. **Không đồng nghĩa với mọi đối tượng được cấp phát:** một pointcut dựa trên vị trí gọi cụ thể hoặc cấu trúc `new` chỉ bao phủ các call site mà nó khớp và cơ chế có thể can thiệp.
3. **Không đồng nghĩa với thân constructor:** một biểu thức `new Child(...)` có thể kéo theo chuỗi thực thi constructor ở lớp cha và lớp con.
4. **Kết quả thành công và thất bại khác nhau:** nếu quá trình tạo ném ngoại lệ, bên gọi **không nhận được tham chiếu mới theo nhánh hoàn tất bình thường**; advice chỉ chạy “sau khi thành công” sẽ không được chạy trong nhánh lỗi đó.

Điểm quan trọng là **nơi gọi** và **nơi định nghĩa constructor** là hai vị trí khác nhau trong chương trình. Một constructor có thể được gọi từ nhiều nơi; từng call site có thể được lựa chọn theo các quy tắc khác nhau khi cơ chế AOP hỗ trợ.

## 4. Điểm can thiệp khi thực thi hàm tạo: constructor execution

Giả sử lớp có constructor:

```java
final class Order {
    private final String id;

    Order(String id) {
        this.id = id;
    }
}
```

Ở đây **constructor execution** nói đến điểm thực thi của constructor `Order(String)`. Đây là góc nhìn **từ phía phần tử đang được thực hiện**.

Một pointcut có thể diễn đạt:

```text
Chọn việc thực thi constructor Order(String).
```

Với những cơ chế hỗ trợ join point loại này, mọi đường tạo đi tới đúng constructor đó có thể là ứng viên, kể cả khi đến từ nhiều call site; song **mức độ bao phủ thực tế phải xác minh bằng kỹ thuật weaving**, không thể suy từ biểu thức pointcut đơn lẻ.

**Không tự suy rằng advice ở “trước constructor execution” chạy trước khi mọi phần của đối tượng được khởi tạo.** Trong Java, việc gọi constructor lớp cha, chạy khởi tạo trường và khối khởi tạo của lớp diễn ra theo trình tự do ngôn ngữ quy định. Một mô hình AOP có thể định nghĩa vùng constructor execution riêng so với vùng object initialization, và bị ràng buộc bởi quy tắc an toàn của JVM về tham chiếu `this` chưa khởi tạo. Thời điểm advice chính xác phải được kiểm tra theo ngữ nghĩa cơ chế được dùng.

## 5. So sánh các loại điểm can thiệp

| Góc nhìn | Constructor call | Constructor execution | Object initialization (nếu mô hình hỗ trợ riêng) |
|---|---|---|---|
| Trọng tâm | **Nơi yêu cầu** tạo đối tượng | **Việc thực thi** một constructor | **Quá trình khởi tạo** một thể hiện |
| Vị trí khái niệm | Phía caller/call site | Phía constructor đích | Ranh giới vòng đời khởi tạo được mô hình định nghĩa |
| Ví dụ mô tả | “Chọn những chỗ gọi `new Order(...)`” | “Chọn chạy `Order(String)`” | “Chọn giai đoạn khởi tạo `Order`” |
| Nhiều nơi tạo dùng cùng constructor | Có thể là nhiều call join point | Cùng định nghĩa constructor được thực thi nhiều lần | Liên quan từng quá trình khởi tạo thể hiện |
| Với kế thừa / `this(...)` | Cần xác định chính xác nơi/lời gọi được mô hình xem là join point | Có thể có nhiều constructor execution trong chuỗi | Cần xác định ngữ nghĩa giai đoạn khởi tạo |
| Kết quả sau khi thành công | Bên gọi nhận kết quả của biểu thức tạo | Constructor cụ thể kết thúc bình thường | Quá trình khởi tạo hoàn tất theo phạm vi định nghĩa |

Cột cuối không phải một “loại join point bắt buộc” của mọi AOP. Các mô hình khác nhau có thể định nghĩa ít loại hơn hoặc tổ chức chúng theo cách khác.

### 5.1. Constructor call và method call không giống nhau

Trong Java, `new Order(...)` là biểu thức tạo thể hiện và gọi constructor. `order.submit()` là lời gọi phương thức thông thường. Một công cụ chỉ có cơ chế chặn **lời gọi phương thức qua đối tượng trung gian** không đương nhiên nhìn thấy biểu thức `new`.

### 5.2. Constructor execution và method execution không giống nhau

Constructor không kế thừa theo cơ chế override như phương thức instance; `new Child(...)` được ràng buộc với constructor phù hợp theo quy tắc ngôn ngữ. Vì vậy, các giải thích về dispatch động của phương thức không thể bê nguyên sang constructor execution.

## 6. Trình tự khởi tạo đối tượng trong Java: phải hiểu trước khi gắn advice

Một biểu thức `new Child()` thông thường không chỉ chạy vài câu lệnh trong thân `Child()`. JVM/JLS còn điều phối việc cấp phát, giá trị mặc định, chuyển qua constructor lớp cha, các trường và khối khởi tạo, rồi mới hoàn tất.

Với đối tượng Java thông thường, có thể hình dung:

```text
Bắt đầu biểu thức tạo đối tượng (new Child(...))
  |
  |  đánh giá các đối số theo quy tắc ngôn ngữ
  |  cấp phát thể hiện, trường có giá trị mặc định ban đầu
  v
Chạy chuỗi constructor theo kế thừa / chuyển tiếp
  |
  |  constructor cha và quá trình khởi tạo cha
  |  khởi tạo trường/instance initializer của lớp con ở bước thích hợp
  |  chạy thân các constructor liên quan
  v
Hoàn tất bình thường → biểu thức new trả về tham chiếu
Hoặc ném ngoại lệ → biểu thức new không trả tham chiếu theo nhánh thành công
```

Sơ đồ cố ý chỉ thể hiện **thứ tự tương đối**; các bước chính xác với constructor `this(...)`, `super(...)`, lớp lồng và kế thừa phải tuân theo Java Language Specification. Không nên đồng nhất “thực thi thân constructor” với toàn bộ thời gian từ đánh giá đối số đến khi tham chiếu được trả về.

### 6.1. Ví dụ Java 17 chạy được: kế thừa và chuyển tiếp constructor

Lưu tệp **`ConstructionOrderDemo.java`**:

```java
public class ConstructionOrderDemo {
    static class Base {
        int baseValue = initializeBase();

        Base() {
            System.out.println("Base constructor body");
        }

        private int initializeBase() {
            System.out.println("Base field initializer");
            return 1;
        }
    }

    static class Child extends Base {
        int childValue = initializeChild();

        Child() {
            this("standard");
            System.out.println("Child() body");
        }

        Child(String label) {
            super();
            System.out.println("Child(String) body: " + label);
        }

        private int initializeChild() {
            System.out.println("Child field initializer");
            return 2;
        }
    }

    public static void main(String[] args) {
        System.out.println("Before new Child()");
        Child child = new Child();
        System.out.println("After new: " + child.baseValue + ", " + child.childValue);
    }
}
```

Biên dịch và chạy:

```bash
javac ConstructionOrderDemo.java
java ConstructionOrderDemo
```

**Stdout chính xác:**

```text
Before new Child()
Base field initializer
Base constructor body
Child field initializer
Child(String) body: standard
Child() body
After new: 1, 2
```

**Giải thích:**

- `main` in `Before new Child()` trước khi gọi biểu thức `new Child()`.
- Constructor `Child()` chuyển tiếp qua `this("standard")`; `Child(String)` gọi `super()`.
- Trường của `Base` được khởi tạo, sau đó thân `Base()` chạy.
- Phần khởi tạo trường của `Child` diễn ra **một lần** trong chuỗi constructor hợp lệ, không lặp lại chỉ vì có `this(...)`.
- `Child(String)` in thông báo, rồi quay về thân `Child()`.
- Chỉ sau khi toàn bộ chuỗi hoàn tất, `main` in `After new: 1, 2`.

**Bài học AOP:** Một biểu thức `new Child()` ở phía caller tạo ra **một lần tạo thể hiện** nhưng liên quan đến việc thực thi **nhiều constructor** (`Base()`, `Child(String)`, `Child()`) trong chuỗi khởi tạo. Nếu một chính sách dựa trên constructor execution được áp dụng ở nhiều mức, số lần advice xuất hiện có thể khác dự đoán “mỗi `new` chỉ có một constructor”.

Đây là quan sát Java thuần; code không tự thực hiện weaving. Mốc advice thực tế phụ thuộc join point mà mô hình AOP định nghĩa.

## 7. Minh họa hai ranh giới: bao bên ngoài nơi gọi và quan sát bên trong constructor

Để quan sát dễ hơn, ví dụ sau dùng **Java thuần**:

- Hàm `atCreationSite(...)` là một wrapper ở **bên ngoài** biểu thức `new`, mô phỏng hành vi bao quanh một vị trí gọi tạo đối tượng.
- Những câu lệnh `[constructor] ...` được viết **bên trong** constructor để mô phỏng quan sát tại phần thân constructor.

**Đây là mô hình trực quan phục vụ học tập, không phải một hệ AOP tự weaving.** Trong hệ AOP thực, một aspect có thể gắn advice bằng weaving theo loại join point được hỗ trợ.

Lưu tệp **`ConstructorBoundaryDemo.java`**:

```java
import java.util.function.Supplier;

public class ConstructorBoundaryDemo {
    static final class Ticket {
        private static int nextId;
        final int id;

        Ticket(boolean reject) {
            System.out.println("[constructor] enter");
            try {
                if (reject) {
                    System.out.println("[constructor] reject");
                    throw new IllegalArgumentException("invalid");
                }
                id = ++nextId;
                System.out.println("[constructor] assigned " + id);
            } finally {
                System.out.println("[constructor] exit");
            }
        }
    }

    static <T> T atCreationSite(Supplier<T> constructorCall) {
        System.out.println("[site] before");
        try {
            T value = constructorCall.get();
            System.out.println("[site] success");
            return value;
        } catch (RuntimeException ex) {
            System.out.println("[site] failure: " + ex.getMessage());
            throw ex;
        }
    }

    public static void main(String[] args) {
        try {
            Ticket first = atCreationSite(() -> new Ticket(false));
            System.out.println("Ticket ready: " + first.id);

            atCreationSite(() -> new Ticket(true));
        } catch (IllegalArgumentException ex) {
            System.out.println("Caller caught: " + ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac ConstructorBoundaryDemo.java
java ConstructorBoundaryDemo
```

**Stdout chính xác:**

```text
[site] before
[constructor] enter
[constructor] assigned 1
[constructor] exit
[site] success
Ticket ready: 1
[site] before
[constructor] enter
[constructor] reject
[constructor] exit
[site] failure: invalid
Caller caught: invalid
```

### 7.1. Có thể rút ra điều gì?

**Lần tạo thành công:** Wrapper ở nơi gọi ghi `[site] before`, constructor thực hiện phần bên trong, sau đó wrapper mới nhận kết quả và ghi `[site] success`. Hai điểm quan sát phục vụ **hai ranh giới khác nhau**.

**Lần tạo thất bại:** Constructor ném `IllegalArgumentException`, nhưng `finally` trong thân constructor vẫn chạy sau khi phần `try` đã bắt đầu; wrapper bắt ngoại lệ và ghi `[site] failure`. Phần `Ticket` không được trả về theo nhánh thành công.

**Hợp đồng của dấu hiệu “after”:** `[constructor] exit` trong `finally` chỉ báo rằng chương trình thoát phạm vi `try` thuộc thân constructor, **không bảo đảm khởi tạo thành công**. Nếu cần thống kê số đối tượng tạo thành công, phải ghi tại nhánh thực sự hoàn tất thành công.

### 7.2. Giới hạn của ví dụ

`atCreationSite` chỉ có tác dụng khi **nơi gọi chủ động dùng wrapper**. Nó không tự chặn mọi `new Ticket(...)` khác. Những lệnh in trong constructor là mã được viết thủ công, không thể coi là advice tự động. Đặc biệt, `try/finally` ở thân constructor **không quan sát được** lỗi xảy ra trước khi thân đó được chạy, chẳng hạn trong chuỗi gọi constructor lớp cha hoặc quá trình khởi tạo trường; vì vậy không được tuyên bố ví dụ đã đo toàn bộ vòng đời khởi tạo.

Ví dụ có `final int id`. Nếu constructor ném ngoại lệ trước khi gán `id`, Java không yêu cầu nhánh ném đó hoàn tất khởi tạo như nhánh trả về bình thường. Nhánh thành công luôn gán giá trị cho `id` trước khi constructor kết thúc.

## 8. Pointcut cho khởi tạo và thực thi constructor nên mô tả gì?

Khi thiết kế một pointcut liên quan đến constructor, nên trả lời các câu hỏi sau:

1. **Loại join point:** chọn *constructor call*, *constructor execution* hay một loại *initialization* (nếu có)?
2. **Loại đối tượng:** chọn constructor của lớp nào, lớp con nào, nhóm kiểu nào?
3. **Chữ ký constructor:** có bao nhiêu tham số, kiểu nào, phạm vi truy cập nào?
4. **Ngữ cảnh động:** có xét đối số thực tế hoặc caller không, và mô hình có cung cấp dữ liệu đó không?
5. **Các đường tạo khác nhau:** đối tượng được tạo qua `new` trực tiếp, một factory, reflection hay con đường đặc biệt khác?
6. **Thời điểm advice:** trước, sau khi thành công, sau khi lỗi, hoặc quanh điểm chọn?
7. **Điều gì được bảo toàn:** kết quả khởi tạo, ngoại lệ, số lần tạo, trạng thái cuối cùng?

Ví dụ pseudocode **độc lập công cụ, không phải cú pháp Java hoặc một thư viện AOP cụ thể**:

```text
aspect ConstructionObservability:
    pointcut selectedCreationSites:
        constructor-call(Order(String)) AND caller-in(BatchImporter)

    pointcut selectedExecutions:
        constructor-execution(Order(String))

    before selectedCreationSites:
        record("requested from importer")

    after-success selectedExecutions:
        record("Order constructor completed successfully")

    after-failure selectedExecutions:
        record("Order constructor failed")
```

Tác dụng minh họa: pointcut đầu tiên chọn **nơi gọi** từ một nhóm caller; pointcut thứ hai chọn **thực thi** của một constructor. Phạm vi phủ có thể khác nhau đáng kể. Các tên `constructor-call`, `after-success`… chỉ là ngôn ngữ diễn đạt trong bài, không cam kết một công cụ nào chấp nhận đúng cú pháp đó.

### 8.1. Điều kiện về chữ ký không phải điều kiện về giá trị

Constructor `Order(String code)` có chữ ký nhận `String`; điều kiện chọn “constructor nhận một `String`” có thể khớp với `new Order("A")`, `new Order("")` và `new Order(null)`. Nếu muốn chỉ chọn mã bắt đầu bằng `"VIP-"`, cần một điều kiện **động** kiểm tra giá trị, khi AOP có cung cấp ngữ cảnh tương ứng.

### 8.2. Cẩn thận với overload

```java
Order()
Order(String code)
Order(String code, int quantity)
```

Ba constructor này là những chữ ký khác nhau. Pointcut chọn `Order(String)` không tự bao phủ cả ba. Nếu một constructor gọi `this(...)` để chuyển tiếp, số lần execution join point và ngữ nghĩa của constructor call join point còn phụ thuộc đúng loại điểm mà mô hình nhận diện.

### 8.3. Điều kiện về kiểu và kế thừa

Một object được tạo bằng `new PremiumOrder(...)` có thể thực thi constructor của cả lớp cha `Order` và lớp con. Pointcut “constructor khai báo trong `Order`” và pointcut “tạo một đối tượng runtime thuộc loại `PremiumOrder`” không đồng nghĩa. Thậm chí ở những thời điểm rất sớm của quá trình khởi tạo, không được tùy tiện truy cập trạng thái của lớp con như thể đã hoàn tất.

## 9. Phân biệt before, after-returning, after-throwing và around khi xây dựng đối tượng

Những kiểu advice phổ biến có thể mang ý nghĩa khác nhau tại join point constructor:

| Advice khái niệm | Điều cần phân biệt |
|---|---|
| **Before** | Xảy ra trước mốc mà mô hình gọi là join point; không mặc nhiên đứng trước mọi bước cấp phát/khởi tạo |
| **After successful completion** | Chỉ khi phần hoạt động được bao quan sát là hoàn tất bình thường |
| **After exceptional completion** | Khi phần hoạt động được bao kết thúc bằng ngoại lệ thuộc phạm vi được cơ chế quan sát |
| **After/finally** | Chạy khi rời phạm vi được bao, bất kể thành công hay lỗi theo semantics của công cụ |
| **Around** | Có thể bao việc tiếp tục thực thi ở join point; quyền thay thế/chặn/đổi kết quả phụ thuộc tính năng và ràng buộc của công cụ |

**Ví dụ khác biệt:** Nếu constructor gán trường rồi kết thúc bình thường nhưng caller ném lỗi ngay sau `new`, một after-success gắn vào constructor execution vẫn có thể thành công, còn khối `try` lớn của caller có thể thất bại. Ngược lại, nếu đánh giá đối số của `new Order(computeId())` ném lỗi **trước khi constructor bắt đầu**, advice chỉ gắn vào constructor execution không có lý do gì phải chạy cho lần đó.

Điều này đặc biệt quan trọng khi đo số “lần yêu cầu tạo”, số “lần constructor bắt đầu”, số “lần hoàn tất”, và số “lần tạo thất bại”: đây là **những số đo khác nhau**.

## 10. Trường hợp đối số lỗi trước khi constructor được thực thi

Hãy xem đoạn Java:

```java
static String getId() {
    throw new IllegalStateException("cannot prepare id");
}

Order item = new Order(getId());
```

Đây là **mã minh họa rời**, không phải chương trình độc lập. Trong ngữ nghĩa Java, biểu thức đối số `getId()` được đánh giá trước khi lời thực thi constructor `Order(String)` tương ứng bắt đầu. Vì `getId()` ném ngoại lệ, thân constructor của `Order` không chạy.

Một điều kiện AOP về **constructor execution** vì thế không thể suy ra rằng có một lần thực thi constructor để advice xử lý trong trường hợp này. Với một **constructor-call join point**, việc bao gồm hay loại trừ giai đoạn đánh giá đối số còn tùy **định nghĩa chính xác của mô hình** và vị trí weaving. Cần kiểm chứng ở cấp ngữ nghĩa/công cụ, không tự giả định advice sẽ thấy mọi lỗi phát sinh từ toàn biểu thức `new`.

## 11. Các con đường tạo đối tượng không chỉ có một từ khóa new ở caller

Java hỗ trợ nhiều cách có được đối tượng. Không phải cách nào cũng hiển thị bằng `new SomeClass(...)` ngay tại mã của caller:

- **Factory method:** caller gọi `OrderFactory.create(...)`; bên trong factory có thể dùng `new`, tái sử dụng thể hiện hoặc trả về một loại đối tượng khác.
- **Reflection:** `Constructor.newInstance(...)` có thể gọi constructor thích hợp qua cơ chế phản chiếu, dù caller không viết biểu thức `new Order(...)` trực tiếp.
- **Cloning:** đối tượng có thể được sao chép theo cơ chế clone; constructor thông thường của lớp không nhất thiết chạy theo cách như `new`.
- **Deserialization:** trong một số cơ chế khôi phục đối tượng, không phải mọi constructor của lớp được khôi phục đều chạy theo chuỗi tạo thể hiện thông thường.
- **Cơ chế runtime/native khác:** mô hình nhận diện join point có thể không quan sát được mọi con đường cấp phát.

Do đó, hai phát biểu phải tách biệt:

1. “Tôi đã chọn **mọi vị trí mã chứa `new Order(...)`** mà công cụ nhìn thấy.”
2. “Tôi đã chọn **mọi lần một đối tượng `Order` xuất hiện trong hệ thống**.”

Phát biểu thứ hai **rộng hơn** và không tự được suy ra từ phát biểu thứ nhất. Nếu yêu cầu là đếm mọi đối tượng thực sự được cấp phát, có thể cần công cụ instrumentation/runtime chuyên biệt hoặc điểm quản lý vòng đời tập trung khác, chứ không thể đảm bảo chỉ bằng một pointcut constructor cụ thể.

## 12. Kế thừa và lời gọi this/super: vì sao số lượng join point dễ bị hiểu sai?

Trong Java, constructor của lớp con cần phối hợp với constructor lớp cha. Ngoài ra, một constructor có thể **chuyển tiếp** sang constructor khác của cùng lớp bằng `this(...)`.

Ví dụ ở phần 6 có một biểu thức `new Child()` nhưng đi qua:

```text
new Child()
  └── Child()
      └── Child(String)
          └── Base()
```

Đây là mô hình quan hệ chuyển tiếp (thứ tự **thực hiện thân** sau lời gọi chuyển tiếp nhìn khác thứ tự mũi tên). Một pointcut chọn constructor execution của `Base()` có thể phù hợp tại lần tạo `Child`, dù mã nguồn caller chỉ trực tiếp yêu cầu `Child()`.

Nếu mục tiêu là “một sự kiện cho mỗi đối tượng `Child` khởi tạo thành công”, việc gắn cùng advice vào **mọi constructor execution** của cả chuỗi có nguy cơ đếm nhiều lần. Nếu mục tiêu là “đo riêng chi phí thực thi mỗi constructor”, quan sát từng constructor lại có ý nghĩa.

**Thiết kế theo đại lượng cần đo**, chẳng hạn:

| Đại lượng | Ranh giới quan sát cần nghĩ đến |
|---|---|
| Bao nhiêu yêu cầu tạo `Child` từ một nhóm caller? | Constructor call ở các nơi gọi tương ứng |
| Bao nhiêu lần `Child(String)` thực thi? | Constructor execution của `Child(String)` |
| Bao nhiêu thể hiện `Child` được khởi tạo thành công? | Điểm hoàn tất khởi tạo thích hợp, cần tránh đếm chuỗi constructor nhiều lần |
| Mất bao lâu để caller nhận một đối tượng sẵn dùng? | Ranh giới bao toàn quá trình tạo được định nghĩa rõ |
| Chi phí một constructor cụ thể? | Ranh giới execution của constructor đó và các phần thực sự được tính vào số đo |

## 13. Trạng thái this chưa hoàn chỉnh và rủi ro của advice khi tạo đối tượng

Việc can thiệp vào constructor nhạy cảm hơn quan sát một phương thức chạy trên đối tượng đã sẵn sàng.

### 13.1. Đọc trường quá sớm

Ngay sau cấp phát, các trường instance có giá trị mặc định; các lệnh khởi tạo trường và thân constructor chưa chắc đã chạy. `final` có thể chưa nhận giá trị được thiết lập trong constructor. Nếu advice chạy ở một mốc sớm được cơ chế cho phép và đọc `this.id` như trạng thái hoàn chỉnh, kết quả có thể sai hoặc gây lỗi.

### 13.2. Để this thoát ra ngoài trong constructor

Một anti-pattern là công bố `this` từ constructor vào callback, bộ lắng nghe, tập đối tượng toàn cục hoặc luồng khác trước khi khởi tạo xong. Khi đó, mã khác có thể quan sát đối tượng ở trạng thái dở dang.

Aspect chạy quá sớm cũng có thể vô tình khiến `this` “thoát” ra, ví dụ đẩy tham chiếu đối tượng vào hệ thống sự kiện. Nguyên tắc: chỉ công bố thể hiện khi hợp đồng đã cho phép và vòng đời thích hợp đã hoàn tất.

### 13.3. Gọi phương thức có thể override trong constructor

Khi một constructor gọi phương thức instance có thể được override, việc dispatch có thể đến phương thức của lớp con ngay cả khi trạng thái lớp con chưa hoàn chỉnh. Nếu advice can thiệp vào đường gọi đó, thứ tự thực thi còn phức tạp hơn. Không dùng advice làm lý do để gọi thêm phương thức overridable trên đối tượng đang xây dựng.

### 13.4. Thay đổi kết quả construction

Một around advice có thể có khả năng điều phối việc tiếp tục, thay thế hoặc bỏ qua hoạt động gốc ở một số mô hình. Nhưng constructor và đối tượng mới có các ràng buộc ngôn ngữ/runtime: không thể mặc định áp dụng mọi thao tác biến đổi vốn có ở method advice cho constructor advice.

Phải kiểm tra kỹ: công cụ có hỗ trợ around cho loại join point này không, có cho phép thay đối tượng hay không, giá trị trả về được định nghĩa thế nào và việc gọi phần gốc nhiều lần có hợp pháp/đúng hợp đồng không. **Không phỏng đoán rằng around constructor luôn tương đương around một hàm trả về đối tượng.**

## 14. Exception, tài nguyên và sự khác nhau giữa “thoát” và “tạo thành công”

Có ít nhất ba trường hợp cần phân biệt:

1. **Lỗi trước khi vào constructor đích:** đánh giá đối số hoặc phần xử lý chuẩn bị có thể thất bại.
2. **Lỗi trong chuỗi khởi tạo:** constructor cha, initializer hoặc constructor đích có thể ném ngoại lệ.
3. **Constructor hoàn tất, caller thất bại về sau:** đối tượng có thể đã được khởi tạo nhưng quy trình nghiệp vụ lớn hơn vẫn thất bại.

Nếu một constructor mở tài nguyên rồi ném ngoại lệ, Java không tự biến advice “after” thành thao tác giải phóng tài nguyên đúng đắn. Mã khởi tạo vẫn cần giữ các bảo đảm an toàn của chính nó, ví dụ giải phóng tài nguyên đã mở khi khởi tạo không thành công. Advice quan sát tốt phải tránh che giấu ngoại lệ gốc hoặc ném ngoại lệ log làm biến dạng nguyên nhân thất bại.

**Sai lầm phổ biến:** coi bộ đếm “số lần constructor execution bắt đầu” là “số đối tượng sử dụng được”. Đếm theo mục tiêu: yêu cầu tạo, thực thi bắt đầu, khởi tạo thành công, hoặc đối tượng được công bố cho phần còn lại của hệ thống đều có ngữ nghĩa riêng.

## 15. Weaving và giới hạn khả năng can thiệp

AOP không bắt buộc có cùng một kiến trúc triển khai. Tùy mô hình:

- **Weaving ở mức nguồn/bytecode hoặc quá trình biên dịch:** có thể nhận diện những loại điểm mà cơ chế trung gian chỉ dựa trên lời gọi method không chặn được, trong phạm vi được hỗ trợ.
- **Weaving khi nạp lớp:** có thể chỉnh mã tại giai đoạn tải lớp nếu runtime/công cụ có hỗ trợ và các lớp liên quan được xử lý đúng phạm vi.
- **Cơ chế trung gian ở thời điểm chạy:** thường chỉ quan sát các lời gọi đi qua ranh giới trung gian đã đặt; không tự nhìn thấy mọi biểu thức `new`.

Các kỹ thuật có hạn chế và chi phí riêng. Trong Java, một dynamic proxy tạo bằng `java.lang.reflect.Proxy` **là proxy cho lời gọi phương thức của giao diện**; bản thân nó không tự chặn mọi lần `new` hay tự thêm advice vào thân constructor. Một factory hoặc wrapper có thể tập trung lời gọi tạo đối tượng, nhưng đó là **một ranh giới gọi có chủ đích**, không có nghĩa một pointcut constructor tự được áp dụng ở mọi nơi.

**Trước khi khẳng định độ bao phủ, phải xác minh ba lớp:**

```text
Cú pháp/điều kiện pointcut
          ∩
Loại join point công cụ hỗ trợ
          ∩
Phạm vi mã/đường thực thi thực sự được weaving
          =
Tập join point mà advice có thể được kích hoạt
```

Pointcut đúng ý tưởng nhưng loại join point không được hỗ trợ hoặc đường gọi không được weaving thì sẽ không tạo ra hành vi mong đợi.

## 16. Một số tình huống nâng cao

### 16.1. Tạo đối tượng trong vòng lặp lớn

Một pointcut áp dụng vào constructor của đối tượng cực kỳ thường xuyên được tạo có thể khiến advice gây chi phí đáng kể. Chi phí này bao gồm kiểm tra điều kiện, ghi log, tạo chuỗi, đo thời gian hoặc đồng bộ dữ liệu thống kê.

Một chiến lược là chọn đối tượng có ý nghĩa quan sát rõ và sampling thích hợp. Nếu cần đếm chính xác tất cả lần tạo, phải kiểm chứng rằng phép đo không làm đổi hành vi hoặc làm quá tải chương trình. Không kết luận hiệu năng AOP từ một phép đo chỉ có `System.out.println`.

### 16.2. Constructor lồng nhau và tạo đối tượng gián tiếp

Constructor `Order()` có thể tự tạo một `Address()`, `LineItem()` hoặc đối tượng khác. Nếu pointcut rộng chọn mọi constructor, một yêu cầu tạo đối tượng nghiệp vụ có thể sinh nhiều sự kiện advice.

Hãy xác định bạn muốn thống kê **đối tượng gốc**, **tất cả thể hiện phụ thuộc**, hay **lần gọi constructor của một loại cụ thể**; tránh gộp chúng thành cùng một số liệu.

### 16.3. Các bất biến (invariants) của đối tượng

Một constructor có thể bảo đảm đối tượng không được công bố nếu dữ liệu không hợp lệ. Pointcut chọn constructor để log điều kiện có thể hợp lý; nhưng advice không nên làm mất hợp đồng “đối tượng chỉ tồn tại ở trạng thái hợp lệ sau khi tạo xong”.

Đặc biệt với bất biến liên quan `final` fields, an toàn luồng và kiểm soát truy cập, cần tránh quan sát/thay đổi trạng thái ở mốc mà lớp chưa hoàn tất khởi tạo.

### 16.4. Factory trả đối tượng có sẵn

```java
Order order = factory.getOrCreate("A-100");
```

Một lần gọi `getOrCreate` không đồng nghĩa một lần constructor được thực thi: factory có thể trả về thể hiện cache. Nếu yêu cầu là “đếm yêu cầu cấp đối tượng”, pointcut ở factory có thể hợp lý hơn. Nếu yêu cầu là “đếm lần tạo thể hiện mới”, điểm tạo thực tế mới liên quan.

### 16.5. Reflection và đường tạo đặc biệt

Một công cụ AOP có thể quan sát việc thực thi constructor được gọi qua reflection nhưng không thấy cùng call site `new` như biểu thức nguồn; hoặc có thể có giới hạn khác. Với cloning và một số deserialization, logic constructor của lớp có thể không chạy như tạo đối tượng thông thường. Vì vậy, một pointcut constructor không bao giờ được mô tả như máy đếm đối tượng tuyệt đối khi chưa kiểm tra tất cả đường tạo cần thiết.

## 17. Hướng dẫn chọn điểm can thiệp đúng mục tiêu

| Yêu cầu | Điều cần chọn/đo | Lưu ý |
|---|---|---|
| Ghi thông tin về lần **yêu cầu** tạo `Order` từ một caller | Call site được xác định | Phụ thuộc các nơi gọi thực sự được weaving |
| Ghi hoạt động của `Order(String)` | Constructor execution | Có thể nhận cả những đường gọi gián tiếp phù hợp |
| Ghi một sự kiện **khởi tạo `Order` thành công** | Hoàn tất đúng vòng đời khởi tạo | Tránh đếm nhiều constructor trong một chuỗi |
| Quan sát tham số hợp lệ | Điều kiện về giá trị đối số ở ranh giới có dữ liệu | Không nhầm kiểu tham số với giá trị; xử lý `null` |
| Đo tổng thời gian caller nhận đối tượng | Ranh giới bao đủ biểu thức tạo cần quan sát | Cần rõ phần đánh giá đối số và khởi tạo có nằm trong phép đo không |
| Bắt thất bại trong khởi tạo | Nhánh ngoại lệ của vùng thích hợp | Lỗi ở giai đoạn sớm có thể xảy ra trước constructor đích |
| Quan sát mọi thể hiện được cấp phát | Cơ chế quan sát cấp phát phù hợp runtime | Constructor pointcut chưa chắc đủ vì đường tạo đặc biệt |

Việc chọn loại join point nên xuất phát từ **câu hỏi cần trả lời**, không xuất phát từ tên advice có sẵn. Trước khi triển khai, diễn đạt một câu rõ ràng: “Tôi đang quan sát một **lần gọi** hay một **lần thực thi**, và như thế nào mới được tính là **thành công**?”

## 18. Bài tập tự kiểm tra

### Bài 1: Tính số lần thực thi constructor

Xét cấu trúc:

```java
class Parent {
    Parent() {}
}

class Child extends Parent {
    Child() {
        this(7);
    }

    Child(int value) {
        super();
    }
}
```

Với `new Child()`, có mấy constructor body của những lớp này được thực thi?

**Đáp án:** ba constructor body: `Parent()`, `Child(int)`, `Child()`, theo thứ tự thực thi thân tương ứng. Đây là **một lần tạo đối tượng `Child`**, không phải ba đối tượng độc lập.

### Bài 2: Phân biệt nơi gọi và nơi thực thi

Hai phương thức `checkout()` và `importBatch()` đều gọi `new Order("A")`. Muốn gắn hành vi **chỉ khi nơi gọi là `importBatch()`**, nên ưu tiên mô tả điểm can thiệp nào nếu mô hình AOP hỗ trợ?

**Đáp án:** điều kiện constructor-call kết hợp ranh giới caller/call site tương ứng. Một pointcut chỉ nói “constructor execution của `Order(String)`” chưa phân biệt được hai nơi gọi nếu không thêm điều kiện ngữ cảnh.

### Bài 3: Điểm khởi tạo thất bại

Nếu `new Order(loadCode())` mà `loadCode()` ném ngoại lệ trước khi trả về, điều gì chắc chắn đúng?

**Đáp án:** constructor `Order(String)` không được thực thi do việc đánh giá đối số thất bại; advice chỉ gắn vào constructor execution đó không thể coi đây là một lần constructor đã bắt đầu. Việc một cơ chế AOP quan sát được sự kiện call thất bại ở giai đoạn nào phải theo semantics cụ thể.

### Bài 4: Kiểm chứng phạm vi AOP

Một dynamic proxy của giao diện `OrderService` chặn được `service.placeOrder()`, nhưng yêu cầu mới là bắt mọi `new Order(...)`. Có thể chỉ thêm điều kiện pointcut và đảm bảo đạt yêu cầu không?

**Đáp án:** không. Trước hết phải xác định cơ chế có **hỗ trợ join point constructor call/execution** không; proxy chặn method qua giao diện không tự chặn `new`. Cần chọn kỹ thuật weaving, điểm factory, hoặc cơ chế quan sát vòng đời phù hợp.

### Bài 5: Đếm lần tạo thành công

Với một biểu thức `new Child()` có chuỗi `Child() → Child(String) → Parent()`, nếu advice tăng một bộ đếm ở đầu *mỗi constructor execution*, số tăng có nhất thiết bằng số đối tượng `Child` khởi tạo thành công?

**Đáp án:** không. Một lần tạo có thể có nhiều constructor execution, và một trong các bước khởi tạo có thể ném ngoại lệ. Bộ đếm ở đầu execution biểu diễn số lần bắt đầu thực thi các constructor được chọn, không đồng nghĩa số thể hiện khởi tạo hoàn tất.

## 19. Ghi nhớ

- **Constructor call** tập trung vào **nơi yêu cầu tạo** đối tượng; **constructor execution** tập trung vào **việc thực thi** constructor cụ thể; **object initialization** có thể là phạm vi riêng nếu mô hình hỗ trợ.
- **Một biểu thức `new` không đồng nghĩa chỉ một constructor execution**, nhất là với `this(...)`, `super(...)` và kế thừa.
- Thân constructor không luôn bao phủ toàn bộ quá trình tạo; lỗi có thể xảy ra khi đánh giá đối số, trong constructor cha hoặc initializer.
- Advice “sau khi thoát” và advice “sau khi thành công” mang ý nghĩa khác nhau. Một lần bắt đầu không đồng nghĩa một đối tượng đã khởi tạo xong.
- **Pointcut là điều kiện chọn; advice là hành vi; weaving quyết định cách kết hợp**, và khả năng hỗ trợ constructor join point khác nhau giữa các cơ chế AOP.
- Không tự cho rằng proxy lời gọi phương thức có thể chặn `new`; không tự cho rằng mọi đối tượng đều đi qua constructor thông thường.
- Khi can thiệp vào khởi tạo, phải bảo toàn thứ tự hợp lệ, ngoại lệ gốc, bất biến của đối tượng và tránh công bố `this` khi chưa hoàn chỉnh.

Cách tư duy bền vững là xác định chính xác **đang muốn quan sát yêu cầu tạo, từng lần thực thi constructor, hay đối tượng đã hoàn tất khởi tạo**. Từ đại lượng đó mới lựa chọn join point, pointcut và lời khuyên xử lý phù hợp với cơ chế AOP cụ thể.
