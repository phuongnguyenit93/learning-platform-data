# Giữ kiểu tường minh khi cần chủ động giới hạn giao diện sử dụng (Java 10+)

## 1. Mục tiêu và tình huống cần áp dụng

`var` được bổ sung cho **khai báo biến cục bộ có biểu thức khởi tạo** từ Java 10. Nó giúp giảm việc lặp tên kiểu khi kiểu có thể suy ra rõ ràng. Tuy nhiên, đôi khi bạn muốn **chủ động lựa chọn kiểu tĩnh của biến là một interface hoặc lớp cha** thay vì để trình biên dịch suy ra lớp triển khai cụ thể.

Ví dụ:

~~~java
List<String> names = new ArrayList<>();
var concreteNames = new ArrayList<String>();
~~~

Với `import java.util.List;` và `import java.util.ArrayList;`:

- `names` có **kiểu tĩnh `List<String>`**: những phương thức bạn có thể gọi được xác định theo hợp đồng `List`.
- `concreteNames` có **kiểu tĩnh `ArrayList<String>`**: bên cạnh phương thức của `List`, biến còn thấy API riêng của `ArrayList`, chẳng hạn `ensureCapacity(int)`.
- Cả hai đều có thể trỏ tới đối tượng `ArrayList<String>`. Khác biệt nằm ở **kiểu tham chiếu tại thời điểm biên dịch**, không phải lớp đối tượng được tạo khi chạy.

Bài học giúp bạn quyết định lúc nào dùng `var` và lúc nào giữ khai báo tường minh như `List<T>`, `Collection<T>`, `Map<K,V>` hoặc interface nghiệp vụ để **giới hạn những thao tác có thể gọi qua biến**, làm rõ hợp đồng và dễ thay đổi implementation.

Nội dung sử dụng các quy tắc còn áp dụng trong Java hiện đại; các ví dụ độc lập được viết cho JDK 17+.

## 2. Kiểu tĩnh của biến quyết định API mà trình biên dịch cho phép gọi

Java kiểm tra các lời gọi phương thức dựa trên **kiểu tĩnh của biểu thức nhận lời gọi**. Điều này vẫn đúng khi đối tượng lúc chạy thuộc một lớp con có thêm phương thức riêng.

Ví dụ minh họa (đặt trong một phương thức):

~~~java
List<String> list = new ArrayList<>();
list.add("An");
String first = list.get(0);    // Hợp lệ: List<E> có get(int)
// list.ensureCapacity(20);   // Lỗi biên dịch: List không khai báo phương thức này

var arrayList = new ArrayList<String>();
arrayList.ensureCapacity(20);  // Hợp lệ: kiểu tĩnh là ArrayList<String>
arrayList.add("Binh");
~~~

**Mục đích của khai báo `List<String>`:** người đọc và trình biên dịch đều nhìn thấy rằng phần code này chỉ cần hợp đồng của một danh sách, không cần điều khiển dung lượng lưu trữ nội bộ của `ArrayList`.

Lợi ích quan trọng là bạn có thể đổi implementation mà không phải thay đổi code chỉ dựa vào `List`:

~~~java
List<String> names = new ArrayList<>();
// Cũng có thể thay dòng trên bằng:
// List<String> names = new LinkedList<>();
~~~

Hai dòng thay thế là **hai phương án độc lập**, không đặt cả hai khai báo `names` trong một khối. Nếu code chỉ dùng các thao tác thuộc `List`, cả hai implementation đều đáp ứng hợp đồng về mặt kiểu. Chúng vẫn có thể khác nhau về hiệu năng, bộ nhớ và những đặc điểm runtime; dùng interface không bảo đảm chúng tương đương về mọi mặt.

**Giới hạn ở đây là giới hạn thao tác qua tham chiếu có kiểu tĩnh đã chọn.** Đây không phải cơ chế bảo mật, cũng không làm biến đối tượng runtime thành một lớp khác.

## 3. Vì sao `var` có thể làm lộ API của implementation?

Khi viết:

~~~java
var names = new ArrayList<String>();
~~~

Kiểu của biểu thức `new ArrayList<String>()` là `ArrayList<String>`, nên `var` suy ra **đúng kiểu ấy**. Từ đó, `names.ensureCapacity(100)` là lời gọi hợp lệ. Nếu mục tiêu của đoạn code chỉ là thao tác theo hợp đồng `List`, cách này vô tình tạo thêm khả năng phụ thuộc vào implementation.

Bảng so sánh:

| Khai báo | Kiểu tĩnh của biến | Có thể gọi `get(int)`? | Có thể gọi `ensureCapacity(int)`? |
| --- | --- | --- | --- |
| `List<String> x = new ArrayList<>();` | `List<String>` | Có | Không |
| `var x = new ArrayList<String>();` | `ArrayList<String>` | Có | Có |
| `var x = (List<String>) new ArrayList<String>();` | `List<String>` | Có | Không |
| `var x = createList();` khi `createList(): List<String>` | `List<String>` | Có | Không |

Các tên biến `x` trong bảng là **những khai báo độc lập**.

Điểm quan trọng: **`var` không tự động suy ra kiểu implementation trong mọi trường hợp**. Nó chỉ suy ra kiểu của **biểu thức khởi tạo**. Nếu biểu thức đã có kiểu interface vì một phương thức trả về interface hoặc vì một phép ép kiểu có chủ đích, `var` cũng có kiểu interface.

Bạn nên ưu tiên viết trực tiếp `List<String> x = new ArrayList<>();` khi muốn thể hiện ranh giới API rõ ràng. Dùng phép ép kiểu ở initializer chỉ để buộc `var` suy ra interface thường khó đọc hơn mà không mang thêm lợi ích.

## 4. Lựa chọn interface vừa đủ thay vì lớp triển khai cụ thể

Không phải mọi đoạn code đều cần toàn bộ API của `List`. Hãy chọn kiểu tĩnh thể hiện đúng số lượng thao tác thực sự cần:

| Hợp đồng cần dùng | Ví dụ kiểu tĩnh | Những khả năng cơ bản |
| --- | --- | --- |
| Chỉ duyệt các phần tử | `Iterable<String>` | Vòng `for-each`, `iterator()` |
| Duyệt và hỏi số lượng, thêm/xóa theo hợp đồng collection | `Collection<String>` | `size()`, `add()`, `remove()`, `iterator()` |
| Truy cập theo vị trí và thao tác danh sách | `List<String>` | `get(int)`, `set(int, E)`, `add(E)` |
| Tương tác với ánh xạ khóa–giá trị | `Map<String, Integer>` | `get(key)`, `put(key,value)`, `containsKey(key)` |

Ví dụ dùng **`Iterable`** khi chỉ cần duyệt:

~~~java
Iterable<String> users = new ArrayList<String>();
for (var user : users) {
    System.out.println(user);
}
// users.size(); // Lỗi biên dịch: Iterable không khai báo size()
~~~

Ví dụ dùng **`List`** khi cần chỉ số:

~~~java
List<String> users = new ArrayList<>();
users.add("Lan");
System.out.println(users.get(0)); // Lan
~~~

Hai ví dụ là các khối độc lập; ở ví dụ thứ nhất, phần thân không được gọi `size()` qua kiểu `Iterable`, dù đối tượng runtime là `ArrayList` và có khả năng tính kích thước.

Chọn interface **phù hợp với công việc**. Đừng chọn kiểu quá hẹp đến mức phải liên tục ép kiểu ngược lại; đó là dấu hiệu hợp đồng ban đầu không phù hợp. Đừng chọn `Object` khi có interface hoặc generic diễn đạt chính xác hơn.

## 5. Interface nghiệp vụ: tránh phụ thuộc vào phương thức dành riêng cho triển khai

Cách chọn kiểu tường minh không chỉ dành cho collection. Giả sử code có một hợp đồng thông báo:

~~~java
interface Notifier {
    String send(String recipient);
}

final class EmailNotifier implements Notifier {
    @Override
    public String send(String recipient) {
        return "email to " + recipient;
    }

    String providerName() {
        return "SMTP";
    }
}
~~~

*Đây là các định nghĩa kiểu dùng trong ví dụ; chương trình độc lập đầy đủ nằm ở mục 8.*

So sánh:

~~~java
Notifier notifier = new EmailNotifier();
notifier.send("Lan");          // Hợp lệ
// notifier.providerName();    // Lỗi: Notifier không khai báo providerName()

var concrete = new EmailNotifier();
concrete.send("Lan");          // Hợp lệ
concrete.providerName();      // Hợp lệ: kiểu tĩnh EmailNotifier
~~~

Nếu mục tiêu của phần code đang viết chỉ là gửi thông báo, khai báo **`Notifier notifier`** làm hợp đồng sử dụng rõ ràng hơn. Sau này bạn có thể tạo `SmsNotifier` hoặc một implementation thử nghiệm khác với cùng interface mà không phải viết lại logic chỉ phụ thuộc `send()`.

**Đa hình vẫn hoạt động:** Khi gọi `notifier.send(...)`, Java có thể chạy implementation override của lớp thực tế. Tuy nhiên, lời gọi phải **hợp lệ theo kiểu tĩnh `Notifier`** trước khi xét dispatch ở runtime.

Nếu code thực sự cần `providerName()`, có thể dùng `EmailNotifier` trong phạm vi đó, hoặc xem xét thiết kế lại interface nếu hành vi ấy thực chất là một phần hợp đồng chung. Không ép kiểu tùy tiện để phá ranh giới API đã chọn.

## 6. Trường hợp `var` vẫn giữ được interface vì kiểu trả về của factory

Khi phương thức khai báo trả về một interface, `var` ở nơi gọi sẽ suy ra **interface đó**:

~~~java
static Notifier createNotifier() {
    return new EmailNotifier();
}

// Trong một phương thức khác:
var notifier = createNotifier(); // Kiểu suy ra Notifier
notifier.send("An");
// notifier.providerName();      // Lỗi biên dịch
~~~

Hai đoạn trên thuộc cùng lớp có định nghĩa `Notifier` và `EmailNotifier`, không phải tệp chạy độc lập.

Ngay cả khi hiện tại `createNotifier()` luôn trả về `new EmailNotifier()`, kiểu **khai báo ở chữ ký** vẫn là `Notifier`. Trình biên dịch không quan sát đối tượng runtime để tăng khả năng truy cập API riêng của `EmailNotifier`.

Tương tự:

~~~java
static List<String> createNames() {
    return new ArrayList<>();
}

// Ở nơi gọi:
var names = createNames(); // Kiểu suy ra List<String>
// names.ensureCapacity(8); // Lỗi: kiểu tĩnh List<String>
~~~

Vì vậy, cách dùng `var` có thể hoàn toàn phù hợp **nếu kiểu khởi tạo đã rõ và đã được giới hạn theo hợp đồng mong muốn**. Vấn đề không nằm ở chữ `var` tự thân; vấn đề là **kiểu tĩnh được suy ra có quá cụ thể hoặc không rõ với người đọc hay không**.

## 7. Thông tin generic cũng là một phần của hợp đồng cần giới hạn

Giới hạn API không chỉ là chọn `List` thay cho `ArrayList`; còn là **giữ chính xác kiểu phần tử**. Xét:

~~~java
List<String> names = new ArrayList<>();
var concreteNames = new ArrayList<String>();
var unknownElements = new ArrayList<>();
~~~

- `names`: kiểu tĩnh `List<String>`.
- `concreteNames`: kiểu tĩnh `ArrayList<String>`.
- `unknownElements`: trong trường hợp constructor rỗng và không có kiểu đích, suy ra `ArrayList<Object>`.

Hai biến đầu đều giúp trình biên dịch ngăn thêm phần tử không phải chuỗi (trừ các trường hợp tương thích theo hệ kiểu). Biến thứ ba chỉ yêu cầu phần tử tương thích `Object`, nên có thể chứa nhiều lớp khác nhau.

~~~java
var unknownElements = new ArrayList<>();
unknownElements.add("Java");
unknownElements.add(10); // Hợp lệ: kiểu phần tử là Object
// unknownElements.get(0).toUpperCase();
// Lỗi biên dịch: get(0) có kiểu Object, không có toUpperCase()
~~~

Đây không phải hành vi kiểu động. Kiểu tĩnh đã được quyết định ngay từ biểu thức khởi tạo; các lệnh `add()` về sau không khiến Java suy lại `ArrayList<String>`.

**Hai cách rõ ràng khi tạo danh sách rỗng có kiểu phần tử cụ thể:**

~~~java
List<String> names = new ArrayList<>();
var namesConcrete = new ArrayList<String>();
~~~

Cách đầu còn thể hiện mục tiêu phụ thuộc interface `List`. Cách thứ hai vẫn giữ generic `String`, nhưng suy ra kiểu triển khai `ArrayList<String>`.

Nếu không cần thay đổi danh sách, một lựa chọn khác là `var names = List.of("An", "Binh");`. Biểu thức `List.of` có kiểu `List<String>` và tạo danh sách không cho sửa cấu trúc. Tuy nhiên, **khả năng sửa đổi là đặc tính của đối tượng và hợp đồng phương thức**, không chỉ của kiểu tĩnh: một biến kiểu `List<String>` vẫn có thể tham chiếu danh sách không sửa được.

## 8. Ví dụ hoàn chỉnh Java 17+: so sánh API và khả năng đổi implementation

Tạo tệp **ExplicitInterfaceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class ExplicitInterfaceDemo {
    interface Notifier {
        String send(String recipient);
    }

    static final class EmailNotifier implements Notifier {
        @Override
        public String send(String recipient) {
            return "email to " + recipient;
        }

        String providerName() {
            return "SMTP";
        }
    }

    static Notifier createNotifier() {
        return new EmailNotifier();
    }

    static String select(List<String> value) {
        return "List";
    }

    static String select(ArrayList<String> value) {
        return "ArrayList";
    }

    public static void main(String[] args) {
        // Giữ hợp đồng List trong kiểu khai báo.
        List<String> names = new ArrayList<>();
        names.add("An");
        System.out.println("names[0] = " + names.get(0));

        // var với constructor cụ thể suy ra ArrayList<String>.
        var concrete = new ArrayList<String>();
        concrete.ensureCapacity(8);
        concrete.add("Binh");
        System.out.println("concrete[0] = " + concrete.get(0));

        // Overload được chọn từ kiểu tĩnh của biến.
        System.out.println("overload names = " + select(names));
        System.out.println("overload concrete = " + select(concrete));

        // Giới hạn API theo interface nghiệp vụ.
        Notifier notifier = new EmailNotifier();
        System.out.println("notifier = " + notifier.send("Lan"));

        // var với new EmailNotifier() giữ kiểu cụ thể.
        var concreteNotifier = new EmailNotifier();
        System.out.println("implementation = "
                + concreteNotifier.providerName());

        // var với factory trả interface vẫn suy ra interface.
        var fromFactory = createNotifier();
        System.out.println("factory = " + fromFactory.send("Minh"));

        // Đổi implementation, giữ kiểu tham chiếu List.
        List<String> replacement = new LinkedList<>();
        replacement.add("Hoa");
        System.out.println("replacement[0] = " + replacement.get(0));

        // names.ensureCapacity(8); // Không hợp lệ: List
        // notifier.providerName();  // Không hợp lệ: Notifier
        // fromFactory.providerName(); // Không hợp lệ: Notifier
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExplicitInterfaceDemo.java
java ExplicitInterfaceDemo
~~~

Kết quả chính xác:

~~~text
names[0] = An
concrete[0] = Binh
overload names = List
overload concrete = ArrayList
notifier = email to Lan
implementation = SMTP
factory = email to Minh
replacement[0] = Hoa
~~~

Giải thích:
1. `names` được khai báo là `List<String>`, nên code chỉ gọi được các thành viên của `List`; `ensureCapacity()` không thuộc API ấy.
2. `concrete` suy ra `ArrayList<String>`, nên `ensureCapacity(8)` hợp lệ. Lệnh này điều chỉnh dung lượng dự phòng của `ArrayList`, **không thay đổi số phần tử** nên kết quả in vẫn chỉ có `Binh`.
3. Hai overload `select(List<String>)` và `select(ArrayList<String>)` được trình biên dịch lựa chọn dựa trên **kiểu tĩnh tại lời gọi**. Vì vậy `select(names)` trả `List` dù đối tượng runtime cũng là `ArrayList`; `select(concrete)` trả `ArrayList`.
4. `notifier` có kiểu interface `Notifier`, nên chỉ nhìn thấy `send()`. Trong cùng lớp, `concreteNotifier` có kiểu `EmailNotifier` và gọi thêm được `providerName()`.
5. `fromFactory` dùng `var` nhưng được suy ra là `Notifier` vì `createNotifier()` trả về kiểu interface. `var` không làm xuất hiện phương thức riêng của lớp runtime.
6. `replacement` tạo `LinkedList` nhưng giữ kiểu `List<String>`. Logic `add`/`get` làm việc qua hợp đồng chung, có thể dùng implementation khác khi phù hợp.

Mục 8 là chương trình chạy độc lập; những đoạn mã ngắn ở các mục khác chỉ minh họa trong ngữ cảnh đã ghi.

## 9. Những giới hạn mà kiểu tường minh **không** bảo đảm

### 9.1. Interface không đồng nghĩa dữ liệu chỉ đọc

~~~java
List<String> values = List.of("A", "B");
// values.add("C"); // Cú pháp hợp lệ theo List nhưng sẽ ném
// UnsupportedOperationException khi thực thi.
~~~

`List` khai báo phương thức `add`, vì vậy trình biên dịch chấp nhận lời gọi về mặt kiểu. Nhưng đối tượng do `List.of` tạo ra không hỗ trợ sửa đổi cấu trúc; lệnh thực thi có thể ném `UnsupportedOperationException`. **Việc khai báo `List` không phải cam kết danh sách có thể sửa.** Nếu cần bảo đảm bất biến, thiết kế và lựa chọn đối tượng phù hợp; không suy luận từ `var` hay tên interface một cách máy móc.

### 9.2. Interface không tự cấm việc ép kiểu hoặc kiểm tra lớp runtime

~~~java
List<String> values = new ArrayList<>();
if (values instanceof ArrayList<String> arrayList) {
    arrayList.ensureCapacity(100);
}
~~~

Trong Java 17+, kiểu `ArrayList<String>` là một kiểu có thể kiểm tra với mẫu `instanceof` thích hợp trong trường hợp này. Tuy nhiên, việc thường xuyên kiểm tra và truy cập API riêng của implementation làm suy yếu lợi ích thiết kế theo interface. Chỉ làm vậy khi nghiệp vụ thực sự cần thao tác riêng và có cơ sở an toàn. Với mục tiêu chỉ duyệt/thêm/xóa phần tử, hãy giữ thao tác qua `List`.

### 9.3. Kiểu tĩnh không vượt qua `private`, `protected` hoặc package-private

Dù khai báo `var obj = new Concrete();` giúp suy ra `Concrete`, Java vẫn áp dụng các quy tắc quyền truy cập thành viên. Bạn không được gọi một phương thức `private` của lớp khác chỉ vì đã suy ra kiểu cụ thể.

### 9.4. Kiểu tường minh ở biến cục bộ không tự thiết kế toàn bộ API

Khi thiết kế thư viện hay service, **tham số phương thức, kiểu trả về và field** thường là nơi quan trọng để thể hiện hợp đồng. `var` cho biến cục bộ không thay thế kiểu khai báo cho các vị trí đó trong Java 17. Ví dụ:

~~~java
static List<String> loadNames() {
    return new ArrayList<>();
}
~~~

Kiểu trả về `List<String>` nói cho người gọi biết hợp đồng được cung cấp. Tại nơi gọi, `var names = loadNames();` sẽ suy ra `List<String>`, nên giới hạn API vẫn được giữ.

## 10. Khi nào nên chủ động giữ kiểu tường minh?

| Tình huống | Nên ưu tiên | Lý do |
| --- | --- | --- |
| Muốn dùng `List` mà không phụ thuộc `ArrayList` | `List<String> users = new ArrayList<>();` | Giới hạn API theo hợp đồng và dễ thay implementation |
| Chỉ cần duyệt phần tử | `Iterable<User> users = ...;` | Thể hiện phạm vi thao tác nhỏ nhất đủ dùng |
| Code gửi thông báo chỉ cần `send` | `Notifier notifier = new EmailNotifier();` | Làm rõ abstraction nghiệp vụ |
| Muốn gọi phương thức riêng của `ArrayList` | `var list = new ArrayList<String>();` hoặc khai báo `ArrayList<String>` | Lớp cụ thể thực sự cần thiết |
| Factory trả về interface đã thiết kế phù hợp | `var service = factory.create();` | `var` vẫn suy ra interface từ chữ ký trả về |
| Tạo collection rỗng cần đảm bảo generic đúng | `List<String> list = new ArrayList<>();` | Thể hiện cả `String` lẫn interface mong muốn |
| Tên kiểu đích giúp người đọc hiểu vai trò biến | Kiểu tường minh phù hợp | Giảm việc người đọc phải truy ngược sang expression |

Không cần ép mọi khai báo về `List` hay `Collection`. Nếu tính năng bạn đang viết thực sự cần API cụ thể, kiểu cụ thể là lựa chọn hợp lý. Điều quan trọng là **mức độ trừu tượng của khai báo phản ánh đúng những thao tác mà phần code được phép phụ thuộc**.

## 11. Các lỗi và hiểu lầm thường gặp

**Hiểu lầm 1: “`var` và `List<String>` luôn giống nhau khi cùng khởi tạo bằng `new ArrayList<String>()`.”**

Không. `var` giữ kiểu biểu thức `ArrayList<String>`; khai báo `List<String>` giữ kiểu interface. Chúng có thể cùng tham chiếu implementation nhưng có danh sách phương thức khả dụng khác nhau.

**Hiểu lầm 2: “Dùng `var` thì chắc chắn phụ thuộc lớp triển khai.”**

Không. `var users = loadUsers();` vẫn suy ra `List<User>` nếu chữ ký `loadUsers()` khai báo trả về `List<User>`. Hãy xem **kiểu của initializer**.

**Hiểu lầm 3: “Khai báo interface làm runtime object biến thành interface.”**

Không. `List<String> users = new ArrayList<>();` vẫn tạo một đối tượng `ArrayList`. Lựa chọn kiểu tham chiếu chỉ ảnh hưởng khả năng truy cập API qua biến và một số quyết định compile time như overload resolution.

**Hiểu lầm 4: “Chọn interface rồi sẽ không thể đổi implementation.”**

Ngược lại, một biến dùng kiểu tĩnh interface giúp thay implementation phù hợp mà không phải đổi các lời gọi đã bám vào hợp đồng. Tuy nhiên, phải đánh giá lại yêu cầu hiệu năng, cách xử lý `null`, thứ tự dữ liệu, khả năng sửa đổi và các hành vi cụ thể liên quan.

**Hiểu lầm 5: “Càng giới hạn interface càng tốt.”**

Giới hạn quá mức khiến code phải cast liên tục hoặc không thể biểu đạt yêu cầu. Chọn **interface nhỏ nhất nhưng đủ dùng**, rồi giữ nguyên ranh giới ấy nếu nó còn đáp ứng nghiệp vụ.

**Hiểu lầm 6: “`List` chắc chắn cho phép sửa dữ liệu.”**

Không. Interface có phương thức `add` nhưng một implementation có thể từ chối thao tác tùy chọn đó. Khả năng sửa đổi của danh sách cần xem hợp đồng và đối tượng thực tế.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `List<String> list = new ArrayList<>();` không cho phép gọi `list.ensureCapacity(20)`?

**Đáp án:** Kiểu tĩnh của `list` là `List<String>`; `ensureCapacity(int)` không được khai báo trong interface `List`.

**Câu 2.** Kiểu suy ra của `var list = new ArrayList<String>();` là gì? Nó có gọi `ensureCapacity(20)` được không?

**Đáp án:** `ArrayList<String>`. Có, vì `ensureCapacity` là phương thức của `ArrayList`.

**Câu 3.** Nếu `loadUsers()` khai báo trả về `List<User>` nhưng bên trong tạo `ArrayList<User>`, `var users = loadUsers();` suy ra kiểu gì?

**Đáp án:** `List<User>`, đúng theo kiểu trả về đã khai báo của phương thức. `var` không tự mở rộng thành `ArrayList<User>` dựa trên lớp runtime.

**Câu 4.** Khai báo `List<String> names = new ArrayList<>();` có giúp thay bằng `new LinkedList<>()` dễ hơn không?

**Đáp án:** Có ở mức hợp đồng tĩnh: code chỉ gọi API `List` thường không cần đổi kiểu khai báo. Nhưng vẫn phải đánh giá hành vi và hiệu năng của implementation mới theo yêu cầu thực tế.

**Câu 5.** Tại sao `var names = new ArrayList<>();` là rủi ro nếu muốn danh sách chuỗi?

**Đáp án:** Constructor rỗng thiếu thông tin kiểu và không có kiểu đích, nên thường suy ra `ArrayList<Object>`. Để giữ kiểu phần tử `String`, dùng `List<String> names = new ArrayList<>();` hoặc `var names = new ArrayList<String>();`.

**Câu 6.** Dùng interface `Notifier` có chặn được mọi cách gọi API riêng của `EmailNotifier` không?

**Đáp án:** Nó hạn chế các lời gọi **qua tham chiếu có kiểu tĩnh `Notifier`** khi biên dịch. Nó không thay đổi lớp runtime, không cấm một tham chiếu khác có kiểu `EmailNotifier`, và không phải ranh giới bảo mật.

**Câu 7.** Trong ví dụ đầy đủ, vì sao `select(names)` và `select(concrete)` gọi hai overload khác nhau?

**Đáp án:** `names` có kiểu tĩnh `List<String>`, còn `concrete` là `ArrayList<String>`. Java giải overload dựa trên kiểu tĩnh và quy tắc áp dụng phương thức ở compile time.

## 13. Ghi nhớ cuối bài

- `var` giúp suy ra **kiểu tĩnh**, nhưng không tự thể hiện **mức độ trừu tượng mong muốn** nếu initializer dùng lớp triển khai cụ thể.
- Khi cần chủ động giới hạn API để code phụ thuộc vào một hợp đồng, hãy viết kiểu tường minh như `List<String>`, `Collection<T>`, `Map<K,V>` hoặc interface nghiệp vụ.
- Một biến khai báo theo interface chỉ thấy **các thành viên mà interface cho phép truy cập**; runtime vẫn có thể sử dụng implementation cụ thể và dynamic dispatch.
- `var` **vẫn phù hợp** khi initializer trả về chính interface đó, chẳng hạn `var service = factory.create();` với kiểu trả về được khai báo rõ.
- Đừng nhầm giới hạn API tĩnh với tính bất biến hay bảo mật; hãy thiết kế và kiểm tra các đặc tính ấy riêng.
- Cân bằng khả năng đọc, mức độ phụ thuộc implementation và kiểu generic chính xác; chọn kiểu **đủ rõ và đủ hẹp cho công việc**.

**Tài liệu tham khảo hiện còn áp dụng:**
- [Oracle — Local Variable Type Inference (JDK 17)](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html)
- [Java Language Specification 17 — Local Variable Declarations (§14.4)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4)
- [OpenJDK — Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide)
