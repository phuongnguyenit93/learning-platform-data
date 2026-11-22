# Object.clone() không gọi constructor thông thường

## 1. Cơ chế quan trọng nhất của Object.clone()

Khi tạo đối tượng bằng `new`, Java chạy chuỗi khởi tạo đối tượng theo quy tắc của ngôn ngữ: gọi constructor thích hợp, thực hiện quá trình khởi tạo instance, và xử lý các constructor trong chuỗi kế thừa. Ngược lại, **`java.lang.Object.clone()` tạo một đối tượng mới nhưng không gọi constructor thông thường của lớp đối tượng được sao chép**. Các instance field initializer và instance initializer block cũng không được chạy lại cho bản sao do chính `Object.clone()` tạo ra.

Thay vì chạy lại logic khởi tạo, `Object.clone()` tạo đối tượng mới cùng lớp runtime và **sao chép giá trị các trường** của đối tượng gốc như bằng phép gán. Các giá trị nguyên thủy được sao chép; các trường tham chiếu được sao chép **tham chiếu**, chứ không tự tạo bản sao của object con.

Điểm khác nhau có thể nhìn qua bảng:

| Hành động | Chạy constructor của đối tượng mới? | Xử lý các trường thế nào? |
| --- | --- | --- |
| `new Example(...)` | Có | Theo các initializer và constructor của class |
| `super.clone()` đi đến `Object.clone()` | **Không** | Sao chép giá trị field từ object gốc sang object mới |
| Constructor sao chép `new Example(other)` | **Có** | Theo logic lập trình viên viết trong constructor |
| Một override `clone()` tự gọi `new Example(...)` | **Có**, vì override gọi `new` | Do chính implementation của override quyết định |

Cần đọc chính xác câu “constructor không chạy”: nó nói về **bản sao do `Object.clone()` thực sự tạo ra**. `clone()` là phương thức có thể được override; một implementation tùy biến hoàn toàn có thể gọi constructor một cách tường minh. Không được suy ra “mọi phương thức có tên `clone` trong mọi thư viện đều không bao giờ gọi constructor”.

## 2. Vì sao Java không khởi tạo lại đối tượng từ đầu?

Javadoc `Object.clone()` mô tả thao tác mặc định bằng ý tưởng:

1. Tạo một instance mới thuộc **cùng lớp runtime** với đối tượng gốc.
2. Sao chép **nội dung từng field** từ đối tượng gốc sang instance mới, tương đương phép gán.
3. Không sao chép đệ quy các object được field tham chiếu: đây là **shallow copy**.
4. Trả về đối tượng mới cho caller.

Ví dụ một object có các trường:

```java
int id = 42;
String label = "A";
int[] scores = {10, 20};
```

Khi cloning bằng `Object.clone()`, bản sao nhận `id = 42`, nhận tham chiếu đến `String` đang được giữ và nhận **cùng tham chiếu** đến mảng `scores`. Không có constructor nào tự tạo lại một mảng mới cho bản sao, dù constructor của class có logic chuẩn hóa hoặc defensive copy mảng.

Vì thế, nếu constructor có lệnh tăng bộ đếm, ghi log, đăng ký object với nơi quản lý, mở kết nối hoặc cấp tài nguyên, những side effect đó **không tự xảy ra lần thứ hai** khi `Object.clone()` sao chép object. Ta cần thiết kế riêng nếu bản sao thực sự phải được đăng ký/cấp tài nguyên độc lập.

Điều này không có nghĩa các **static initializer** là quy trình cloning. Class phải được khởi tạo theo quy tắc chung trước khi các thao tác tương ứng được thực hiện; `Object.clone()` không chạy lại static initializer, constructor hoặc instance initializer cho bản sao. Không nên dùng bộ đếm constructor làm số lượng instance tuyệt đối nếu class cho phép clone.

## 3. Java 17: chứng minh constructor và instance initializer không chạy lại

Ví dụ dưới đây có hai bộ đếm: một cho **instance initializer block**, một cho **constructor**. Cả hai đều tăng khi dùng `new`, nhưng không tăng khi gọi `clone()` kế thừa hành vi của `Object.clone()`.

```java
public class CloneConstructorDemo {
    static final class TrackedItem implements Cloneable {
        static int initializerRuns;
        static int constructorCalls;

        final int id;
        final int[] scores;

        {
            initializerRuns++;
        }

        TrackedItem(int id, int[] input) {
            constructorCalls++;
            this.id = id;
            this.scores = input.clone();
        }

        @Override
        public TrackedItem clone() {
            try {
                return (TrackedItem) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        TrackedItem original = new TrackedItem(7, new int[] {10, 20});
        System.out.println(TrackedItem.initializerRuns);
        System.out.println(TrackedItem.constructorCalls);

        TrackedItem copy = original.clone();
        System.out.println(TrackedItem.initializerRuns);
        System.out.println(TrackedItem.constructorCalls);

        System.out.println(original != copy);
        System.out.println(original.id == copy.id);
        System.out.println(original.scores == copy.scores);

        copy.scores[0] = 99;
        System.out.println(original.scores[0]);
    }
}
```

Lưu tệp `CloneConstructorDemo.java` rồi chạy:

```bash
javac CloneConstructorDemo.java
java CloneConstructorDemo
```

Đầu ra chính xác:

```text
1
1
1
1
true
true
true
99
```

Giải thích:

1. `new TrackedItem(...)` chạy instance initializer và constructor, nên hai bộ đếm lần lượt đều bằng `1`.
2. `original.clone()` gọi `super.clone()` và đi đến `Object.clone()`. Sau cloning, hai bộ đếm **vẫn bằng `1`**: không có initializer hoặc constructor thông thường nào được chạy lại cho bản sao.
3. `original != copy` là `true`: có một object mới.
4. `original.id == copy.id` là `true`: giá trị `int` được sao chép.
5. `original.scores == copy.scores` là `true`: trường `scores` của cả hai object trỏ đến **cùng mảng**.
6. Sửa `copy.scores[0]` làm `original.scores[0]` đổi thành `99`. Đây là hậu quả của **shallow copy**, không phải chạy constructor lần thứ hai.

Constructor đã clone mảng đầu vào để bảo vệ object gốc khỏi mutation qua tham số `input`. Nhưng `Object.clone()` **không chạy lại** phần `input.clone()` đó, nên bản sao vẫn chia sẻ mảng nội bộ của object gốc.

## 4. Cloneable và quyền truy cập Object.clone()

`Object.clone()` có phạm vi truy cập `protected` và khai báo `throws CloneNotSupportedException`. Không phải bất kỳ object nào cũng có thể được gọi `clone()` công khai từ code ngoài class.

`java.lang.Cloneable` là **marker interface**: nó không khai báo phương thức `clone`. Nó chỉ đánh dấu rằng các instance của class được phép clone bằng cơ chế `Object.clone()`. Nếu đối tượng không triển khai `Cloneable`, việc gọi đến `Object.clone()` sẽ phát sinh `CloneNotSupportedException`. **Mảng Java** là ngoại lệ tiện dụng: các kiểu mảng triển khai `Cloneable` và có thao tác `clone()` public.

Đối với class hỗ trợ cloning, mẫu thường gặp là:

```java
@Override
public MyType clone() {
    try {
        return (MyType) super.clone();
    } catch (CloneNotSupportedException ex) {
        throw new AssertionError(ex);
    }
}
```

Đây là đoạn minh họa **bên trong class `MyType implements Cloneable`**, không phải tệp độc lập. Nó công khai phương thức `clone`, sử dụng kiểu trả về cụ thể và chuyển checked exception thành lỗi không mong đợi khi class đã cam kết hỗ trợ clone.

**Không được nghĩ chỉ cần `implements Cloneable` thì tự nhiên class có một phương thức `clone()` public.** Interface ấy không khai báo phương thức nào; nếu muốn code ngoài gọi được, cần API public phù hợp.

Ví dụ minh họa lỗi khi chưa thực hiện `Cloneable`:

```java
public class CloneableRequirementDemo {
    static final class NoCloneSupport {
        @Override
        public NoCloneSupport clone() throws CloneNotSupportedException {
            return (NoCloneSupport) super.clone();
        }
    }

    public static void main(String[] args) {
        try {
            new NoCloneSupport().clone();
            System.out.println("Unexpected success");
        } catch (CloneNotSupportedException ex) {
            System.out.println("CloneNotSupportedException");
        }
    }
}
```

Chạy `javac CloneableRequirementDemo.java` và `java CloneableRequirementDemo`:

```text
CloneNotSupportedException
```

Ở đây phương thức `clone()` là public nên gọi được, nhưng instance không phải `Cloneable`. Do đó `Object.clone()` từ chối cloning. Một implementation tự tạo object bằng `new` có thể chọn hành vi khác, nhưng đó là quyết định riêng của implementation, không phải cơ chế mặc định của `Object.clone()`.

## 5. Object.clone() sao chép trường final như thế nào?

Khi constructor tạo một object, nó thường gán các field `final` trong quá trình khởi tạo. Trong ví dụ đầu, `id` và `scores` đều là `final`.

Khi `Object.clone()` tạo bản sao, field `final` cũng **nhận giá trị được sao chép** từ object gốc. Điều đó không có nghĩa constructor được gọi ngầm, cũng không có nghĩa code Java của class có thể gán lại field `final` sau khi clone.

- Với `final int id`, bản sao giữ cùng số nguyên `id`.
- Với `final int[] scores`, bản sao giữ **cùng tham chiếu mảng**, dù mảng đó vẫn mutable.
- Nếu code muốn shallow clone trước rồi thay `scores` bằng một mảng khác để thành deep copy, thông thường **không thể gán lại** field `final` trong phương thức `clone()` như đối với field thông thường.

Hãy phân biệt tính **final của biến tham chiếu** và tính **bất biến của object được tham chiếu**. `final` không biến `int[]` thành mảng không thể sửa.

Nếu kiểu dữ liệu thật sự cần field `final` và defensive copy sâu, **copy constructor hoặc static factory** thường làm ý định rõ hơn việc cố điều chỉnh field `final` sau `super.clone()`.

## 6. Shallow copy không giống deep copy

`Object.clone()` mặc định sao chép giá trị của field ở **một lớp đối tượng**, không duyệt toàn bộ object graph.

| Dạng trường | Sau `Object.clone()` | Nguy cơ |
| --- | --- | --- |
| `int`, `boolean` và primitive khác | Giá trị được sao chép | Không có shared mutable object từ riêng primitive |
| `String` | Sao chép tham chiếu | Thường chấp nhận được vì `String` bất biến |
| `int[]` | Sao chép tham chiếu | Hai object chia sẻ mảng mutable |
| `ArrayList<?>` | Sao chép tham chiếu | Hai object chia sẻ cùng danh sách |
| Object con mutable | Sao chép tham chiếu | Sửa object con có thể ảnh hưởng cả hai |
| Object con bất biến | Sao chép tham chiếu | Thường có thể chia sẻ an toàn theo hợp đồng của kiểu |

“Deep copy” không phải một thao tác duy nhất mà `Object.clone()` mặc định thực hiện. Với object graph phức tạp, cần quyết định phần nào phải độc lập, phần nào được chia sẻ, xử lý vòng tham chiếu và tính chất tài nguyên bên ngoài ra sao.

Một bản sao sâu cho trường `int[]` có thể đơn giản là `array.clone()`. Nhưng với `List<MutableThing>`, chỉ `new ArrayList<>(list)` sao chép cấu trúc danh sách, **chưa sao chép các object phần tử**.

### Override clone để sao chép thêm mảng mutable

Ví dụ sau sử dụng field mảng không final để minh họa cách override `clone()` chủ động tạo bản sao độc lập cho mảng.

```java
public class DeepCopyCloneDemo {
    static final class Sample implements Cloneable {
        private int[] values;

        Sample(int[] values) {
            this.values = values.clone();
        }

        @Override
        public Sample clone() {
            try {
                Sample copied = (Sample) super.clone();
                copied.values = values.clone();
                return copied;
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        int first() {
            return values[0];
        }

        void changeFirst(int number) {
            values[0] = number;
        }

        boolean sharesArrayWith(Sample other) {
            return values == other.values;
        }
    }

    public static void main(String[] args) {
        Sample original = new Sample(new int[] {4, 5});
        Sample copied = original.clone();

        System.out.println(original != copied);
        System.out.println(original.sharesArrayWith(copied));

        copied.changeFirst(99);
        System.out.println(original.first());
        System.out.println(copied.first());
    }
}
```

Lưu thành `DeepCopyCloneDemo.java` và chạy:

```bash
javac DeepCopyCloneDemo.java
java DeepCopyCloneDemo
```

Đầu ra:

```text
true
false
4
99
```

Ở đây `super.clone()` vẫn **không gọi constructor**. Sau đó code trong override tạo một mảng mới bằng `values.clone()` và gán nó vào field mutable của bản sao. Vì vậy hai object độc lập về mảng.

Không suy luận rằng “override `clone` luôn tạo deep copy”: ví dụ này chỉ làm sâu thêm đúng **một trường mảng nguyên thủy một chiều**. Với cấu trúc lồng nhau, phần tử mutable hoặc tài nguyên đặc biệt, phải xét thêm các mối liên hệ.

## 7. Copy constructor: một lựa chọn có constructor thật sự

Nếu muốn chủ động chạy logic khởi tạo và kiểm soát các trường `final`, có thể thiết kế **copy constructor**. Nó không phải `Object.clone()`, mà là một lời gọi `new` thông thường:

```java
public class CopyConstructorDemo {
    static final class Snapshot {
        static int constructorCalls;
        final int[] samples;

        Snapshot(int[] samples) {
            constructorCalls++;
            this.samples = samples.clone();
        }

        Snapshot(Snapshot source) {
            this(source.samples);
        }
    }

    public static void main(String[] args) {
        Snapshot first = new Snapshot(new int[] {1, 2});
        Snapshot second = new Snapshot(first);

        System.out.println(Snapshot.constructorCalls);
        System.out.println(first != second);
        System.out.println(first.samples != second.samples);

        second.samples[0] = 9;
        System.out.println(first.samples[0]);
        System.out.println(second.samples[0]);
    }
}
```

Lưu `CopyConstructorDemo.java` và chạy:

```bash
javac CopyConstructorDemo.java
java CopyConstructorDemo
```

Kết quả:

```text
2
true
true
1
9
```

Copy constructor gọi constructor khác bằng `this(source.samples)`, và logic `samples.clone()` thực sự chạy để giữ mảng riêng. Vì dùng `new`, bộ đếm constructor tăng hai lần cho hai object. Với `Object.clone()` ở ví dụ đầu, chỉ constructor của object ban đầu được gọi.

Ưu điểm của cách này là quy trình tạo bản sao được thể hiện rõ: chọn field nào copy, dữ liệu nào chuẩn hóa, và cách gán field `final`. Nhược điểm là cần định nghĩa chính sách cho các lớp kế thừa hoặc runtime subtype nếu class có khả năng được subclass; bản sao do copy constructor của một class không tự bảo đảm giữ nguyên lớp runtime của object con.

## 8. Mảng Java có clone() riêng

Mọi mảng Java hỗ trợ `clone()` và trả về mảng **mới** cùng kiểu, cùng độ dài, sao chép các phần tử cấp đầu tiên. Đây là trường hợp đặc biệt dễ dùng, không yêu cầu lập trình viên tự viết `implements Cloneable`.

```java
public class ArrayCloneDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        int[] copied = source.clone();

        System.out.println(source != copied);
        System.out.println(source[0] == copied[0]);

        copied[0] = 8;
        System.out.println(source[0]);

        int[][] matrix = {{1, 2}, {3, 4}};
        int[][] outerCopy = matrix.clone();

        System.out.println(matrix != outerCopy);
        System.out.println(matrix[0] == outerCopy[0]);

        outerCopy[0][0] = 99;
        System.out.println(matrix[0][0]);
    }
}
```

Lưu `ArrayCloneDemo.java` và chạy:

```bash
javac ArrayCloneDemo.java
java ArrayCloneDemo
```

Đầu ra:

```text
true
true
1
true
true
99
```

Một mảng `int[]` có các phần tử nguyên thủy, nên clone của nó tạo bản sao đủ độc lập đối với những số nguyên bên trong. Một mảng `int[][]` lại có các phần tử cấp ngoài là các tham chiếu tới mảng con. Clone mảng ngoài chỉ sao chép những tham chiếu đó; mảng con vẫn được chia sẻ.

Đây là lý do **clone một mảng nhiều chiều không đồng nghĩa deep clone tất cả các chiều**.

## 9. Object.clone() và bất biến khởi tạo

Constructor thường giữ những trách nhiệm ngoài gán giá trị field:

- Kiểm tra tham số `null`, giới hạn hoặc định dạng dữ liệu.
- Chuẩn hóa, sao chép phòng vệ các input mutable.
- Tăng bộ đếm, ghi log hoặc ghi nhận lần tạo đối tượng.
- Gán những field phái sinh từ các tham số đầu vào.
- Đăng ký object với các thành phần khác hoặc cấp tài nguyên.

Vì `Object.clone()` không chạy constructor, **không công việc nào ở trên được tự động làm lại**. Giá trị field đã có được sao chép, nhưng các side effect khởi tạo độc lập không xuất hiện lần thứ hai.

Điều này tạo ra những câu hỏi thiết kế:

1. Nếu object có file handle hoặc socket, bản sao cần chia sẻ tài nguyên, giữ tham chiếu, hay không nên được clone?
2. Nếu constructor đăng ký object vào một registry, clone có cần đăng ký riêng hay bị cấm?
3. Nếu field là mảng mutable được constructor sao chép để phòng vệ, clone có cần thêm một lần copy để tránh aliasing không?
4. Nếu một “ID duy nhất” được constructor sinh ra, bản sao nên giữ cùng ID hay cần ID mới? Câu trả lời phụ thuộc ngữ nghĩa *entity* hay *value*.
5. Nếu một lớp cha định nghĩa `clone()` và lớp con thêm trường mutable, lớp con đã thực hiện deep copy đúng phần trạng thái mới chưa?

Không mặc định rằng việc bỏ qua constructor làm tất cả object clone trở nên không hợp lệ. Nếu object gốc có trạng thái hợp lệ và bản sao chỉ cần cùng giá trị field, shallow clone có thể đáp ứng mục tiêu. **Vấn đề là trách nhiệm thiết kế của constructor không tự được tái thực hiện.**

Không nên dùng constructor counter làm “đếm chính xác mọi instance đang tồn tại” nếu đường tạo instance bao gồm `Object.clone()`. Cũng không nên dùng cloning để lách quy tắc khởi tạo/kiểm tra bắt buộc của ứng dụng.

## 10. Phân biệt yêu cầu chính thức, khuyến nghị và chi tiết triển khai

| Phát biểu | Phân loại | Vì sao |
| --- | --- | --- |
| “`Object.clone()` tạo instance mới và sao chép giá trị field từ object gốc.” | **Hợp đồng của phương thức** | Được API mô tả trực tiếp |
| “`Object.clone()` không chạy constructor thông thường cho bản sao.” | **Hành vi của cơ chế mặc định** | Sao chép field thay vì khởi tạo qua constructor |
| “Clone mặc định sao chép sâu mọi object được tham chiếu.” | **Sai** | Clone mặc định là shallow copy |
| “Class muốn dùng `Object.clone()` cần thực hiện `Cloneable`; nếu không, phát sinh `CloneNotSupportedException`.” | **Hợp đồng của cơ chế mặc định** | `Cloneable` là marker interface |
| “`Cloneable` cung cấp sẵn phương thức `clone()` public.” | **Sai** | Interface không khai báo `clone` |
| “Mọi override `clone()` đều không bao giờ gọi constructor.” | **Sai** | Override tùy biến có thể gọi `new` |
| “Sao chép object có field mutable nên cân nhắc defensive copy.” | **Khuyến nghị thiết kế** | Tránh chia sẻ trạng thái ngoài ý muốn |
| “Chỉ cần `super.clone()` luôn an toàn với socket, thread, lock, file handle.” | **Sai** | Các tài nguyên có hợp đồng riêng, không được sao chép tự động đúng ngữ nghĩa |
| “Nên dùng copy constructor/static factory khi cần khởi tạo rõ ràng hoặc field `final`.” | **Khuyến nghị** | Thường kiểm soát invariant và chính sách sao chép dễ hơn |
| “`x.clone().equals(x)` bắt buộc đúng với mọi class.” | **Không phải cam kết tuyệt đối** | Javadoc `Object.clone` trình bày đây là ý định thường gặp, không phải yêu cầu tuyệt đối |
| “`Object.clone()` luôn giữ thứ tự của classloader, cách cấp phát địa chỉ hoặc giá trị hash identity giống object cũ.” | **Không có cam kết như vậy** | Các chi tiết JVM không phải nội dung contract của clone |

Theo Javadoc `Object.clone()`, thường mong `x.clone() != x` và cùng class runtime; các nhận định như `x.clone().equals(x)` được trình bày với mức độ kỳ vọng, không phải nghĩa vụ tuyệt đối cho mọi implementation override `clone()`. Điều quan trọng hơn khi thiết kế API là công bố **chính sách sao chép** của chính class đó.

## 11. Lỗi phổ biến

**Lỗi 1 — nghĩ clone chạy lại constructor.** Dẫn đến dự đoán sai số lần initializer/constructor gọi, logic đăng ký object, mảng được copy hoặc ID được tạo. Hãy nhớ hành vi chuẩn của `Object.clone()` là sao chép field.

**Lỗi 2 — tưởng field final không được clone.** `Object.clone()` sao chép giá trị field final; nó không cần gọi constructor để gán lại từ source code. Tuy nhiên, field final chứa tham chiếu mutable có thể tiếp tục chia sẻ object bên trong.

**Lỗi 3 — tin rằng implements Cloneable đủ để có API clone public.** `Cloneable` chỉ là marker; class cần tự công bố phương thức clone nếu caller ngoài class cần dùng.

**Lỗi 4 — trả `super.clone()` rồi cho rằng đó là deep copy.** Tất cả object con được tham chiếu vẫn có thể chia sẻ. Với `List`, mảng, object mutable và tài nguyên ngoài, phải chỉ rõ chính sách.

**Lỗi 5 — clone một mảng hai chiều rồi tưởng sao chép cả các hàng.** `matrix.clone()` chỉ sao chép mảng ngoài, các mảng con vẫn cùng tham chiếu.

**Lỗi 6 — sao chép tài nguyên mà không kiểm tra vòng đời.** File handle, lock, stream hoặc socket có thể không có ngữ nghĩa sao chép phù hợp. Có kiểu nên cung cấp một factory tạo tài nguyên mới; có kiểu nên cấm cloning.

**Lỗi 7 — dùng cloning để tạo entity mới nhưng vô tình giữ ID gốc.** Nếu ID phải duy nhất, việc giữ lại trường định danh bằng shallow clone có thể trái yêu cầu nghiệp vụ, dù cơ chế `Object.clone` hoạt động đúng như API công bố.

## 12. Câu hỏi tự luyện

**Câu 1.** Constructor tăng `static int created` mỗi khi chạy. Sau một lần `new Item()` rồi một lần `super.clone()` tạo bản sao, `created` mặc định tăng mấy lần?

**Đáp án:** Một lần, nếu không có override tự tăng bộ đếm hay gọi thêm constructor. `Object.clone()` không chạy constructor thông thường cho bản sao.

**Câu 2.** Một field `final int[] data` có trong object gốc. Sau `Object.clone()`, hai object giữ hai mảng độc lập không?

**Đáp án:** Không. Field final được sao chép ở mức **tham chiếu**, nên mặc định chúng cùng trỏ đến một mảng. Final không làm phần tử mảng bất biến.

**Câu 3.** Class triển khai `Cloneable` nhưng không công bố public `clone()`. Code bên ngoài có chắc gọi được `instance.clone()` không?

**Đáp án:** Không. `Object.clone` là `protected` và `Cloneable` không khai báo phương thức public.

**Câu 4.** Trong một override `clone()`, tác giả viết `return new MyType(this);`. Constructor có chạy không?

**Đáp án:** Có. Đó là lời gọi `new` trong implementation tùy biến; nó không phải hành vi tạo object của `Object.clone()`.

**Câu 5.** Tại sao không nên dùng shallow clone như giải pháp chung cho object đang sở hữu socket?

**Đáp án:** Bản sao có thể chia sẻ tham chiếu tài nguyên và trạng thái quản lý vòng đời. Sao chép giá trị field không tự tạo một socket độc lập hay đồng bộ các quy tắc đóng/mở.

**Câu 6.** `int[][] copied = matrix.clone();` có bảo đảm `matrix[0] != copied[0]` không?

**Đáp án:** Không. Clone mảng ngoài sao chép tham chiếu tới các mảng con. Hai hàng tương ứng vẫn có thể là cùng một object.

## 13. Ghi nhớ

- **`Object.clone()` không gọi constructor thông thường hay instance initializer của bản sao.** Nó tạo instance mới và sao chép giá trị field.
- **Shallow copy:** primitive được sao chép theo giá trị; trường tham chiếu giữ cùng object được trỏ đến, trừ khi override chủ động sao chép thêm.
- `Cloneable` là marker interface; `Object.clone` là `protected` và có thể ném `CloneNotSupportedException`.
- Field `final` vẫn được sao chép bởi cơ chế clone; final reference không tương đương deep immutability.
- Override `clone()` **có thể** tự gọi constructor, factory hoặc logic deep copy; phải đọc implementation cụ thể.
- Mảng có `clone()` riêng; `int[]` copy các số độc lập, `int[][]` chỉ copy mảng ngoài.
- Dùng **copy constructor** hoặc factory khi cần kiểm soát khởi tạo và bất biến rõ ràng, nhất là với object có field final hay tài nguyên khó sao chép.
- Khi xây API sao chép, hãy công bố rõ field nào chia sẻ, field nào độc lập, và cách xử lý ID, registry cùng tài nguyên.

Đối chiếu tài liệu chính thức: [`Object.clone()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()), [`Cloneable` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html), [Java Language Specification — Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html).
