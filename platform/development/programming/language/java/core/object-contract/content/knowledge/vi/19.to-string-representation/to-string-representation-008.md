# Tránh đệ quy vô hạn trong quan hệ tham chiếu hai chiều khi viết `toString()`

## 1. Vấn đề: hai đối tượng cùng tham chiếu ngược về nhau

Trong Java, quan hệ **hai chiều** xuất hiện khi một đối tượng giữ tham chiếu tới đối tượng khác và đối tượng kia cũng giữ tham chiếu quay lại. Ví dụ:

- `Department` có danh sách `Employee`;
- mỗi `Employee` lại có tham chiếu `department`;
- cả hai lớp đều override `toString()` để in toàn bộ những trường tham chiếu đó.

Một đối tượng `Department` có thể được xem là gốc của đồ thị:

```text
Department(ENG)
    |
    | employees
    v
Employee(An)
    |
    | department
    +-------------------> Department(ENG)  (chính đối tượng ban đầu)
```

Nếu `Department.toString()` in danh sách nhân viên bằng `employees.toString()`, danh sách lại in từng `Employee.toString()`, rồi `Employee.toString()` tiếp tục in cả `Department`, chương trình quay lại điểm xuất phát. Không có điều kiện dừng, chuỗi gọi sẽ lặp:

```text
Department.toString()
  -> List.toString()
     -> Employee.toString()
        -> Department.toString()
           -> List.toString()
              -> Employee.toString()
                 -> ...
```

Vấn đề xảy ra **dù dữ liệu mô hình hoàn toàn hợp lệ**. Quan hệ hai chiều không sai; việc duyệt tất cả tham chiếu trong `toString()` mà thiếu quy tắc dừng mới là nguyên nhân.

Khi độ sâu lời gọi tăng quá khả năng của stack, JVM thường ném `StackOverflowError`. Không nên dùng `catch (StackOverflowError)` như một chiến lược bình thường: vào lúc đó stack đã cạn và việc phục hồi/in tiếp có thể không đáng tin cậy.

## 2. Vì sao phép nối chuỗi cũng có thể kích hoạt lỗi?

Không nhất thiết phải gọi `obj.toString()` tường minh. Những cách thông dụng sau có thể dẫn tới lời gọi `toString()` trên đối tượng khác `null`:

- `System.out.println(obj)` và `String.valueOf(obj)`;
- `"data=" + obj` hoặc `StringBuilder.append(obj)`;
- phép định dạng chuỗi có đối số đối tượng, chẳng hạn `String.format("%s", obj)`;
- `Collection.toString()` hoặc `Map.toString()` khi chúng trình bày các phần tử, khóa hay giá trị;
- log/debugger/IDE khi chúng chọn hiển thị đối tượng thông qua `toString()`.

Việc log thông qua framework có thể đánh giá đối số theo nhiều thời điểm khác nhau, nhưng khi cuối cùng nó định dạng đối tượng bằng `toString()` thì vẫn tồn tại rủi ro. Không nên giả định một câu lệnh log vô hại chỉ vì người lập trình không gõ tên phương thức.

Đặc biệt, gọi `employees.toString()` không làm Java tự biết rằng trường `employee.department` cần bị bỏ qua. Một số cấu trúc chuẩn có cơ chế bảo vệ **tự chứa trực tiếp** trong cách in của riêng chúng, nhưng không thể suy rộng điều đó thành khả năng nhận biết mọi vòng tham chiếu qua nhiều đối tượng ứng dụng.

## 3. Mẫu cài đặt dẫn đến đệ quy vô hạn

Giả sử `Department` và `Employee` có các trường `employees` và `department`. Đây là **hai phương thức lỗi minh họa**, không phải chương trình Java độc lập:

```java
// Bên trong Department:
@Override
public String toString() {
    return "Department{employees=" + employees + "}";
}

// Bên trong Employee:
@Override
public String toString() {
    return "Employee{department=" + department + "}";
}
```

Diễn biến với một department có nhân viên thuộc chính department đó:

1. In `Department` làm `employees` được chuyển thành chuỗi.
2. Danh sách chuyển các phần tử thành chuỗi, gọi `Employee.toString()`.
3. `Employee.toString()` chuyển `department` thành chuỗi.
4. Đây chính là `Department` ở bước 1. Chuỗi gọi quay lại đầu và tiếp tục vô hạn.

Sự có mặt của `final` trên tham chiếu không loại bỏ vòng. Một đồ thị có thể bất biến về cấu trúc nhưng vẫn chứa chu trình; `toString()` duyệt toàn bộ các cạnh của chu trình sẽ tiếp tục lặp.

Cũng không thể giải quyết gốc rễ bằng cách “tăng stack size” để in thêm nhiều tầng: nó chỉ có thể trì hoãn thời điểm tràn, không đưa vào điều kiện dừng.

## 4. Cách đơn giản và thường nên dùng: chỉ in thuộc tính cần thiết

Phần lớn `toString()` dùng để hỗ trợ quan sát nhanh, debug hoặc log. Nó **không cần trình bày đầy đủ đồ thị đối tượng**.

Với ví dụ Department ↔ Employee, thiết kế gọn và dễ kiểm soát là:

- `Department.toString()` hiển thị `code` và số lượng nhân viên, thay vì in mỗi nhân viên.
- `Employee.toString()` hiển thị `name` và `department.code`, thay vì gọi `department.toString()`.
- Chọn giá trị hiển thị ổn định, ngắn và hữu ích; tránh vô tình kéo theo nhiều đối tượng hoặc dữ liệu nhạy cảm.

Quy tắc thực hành: ở quan hệ hai chiều, ít nhất **một hướng trình bày phải dừng ở thông tin nhận diện**, ví dụ ID, mã, số lượng, hoặc ký hiệu `<omitted>`.

Có thể chọn `departmentId` thay cho đối tượng `department` khi hiển thị nhân viên. Đây là lựa chọn biểu diễn trong `toString()`; không nhất thiết phải bỏ quan hệ hai chiều khỏi mô hình nghiệp vụ.

Nếu cần xuất cả cấu trúc sang JSON hoặc một định dạng trao đổi, hãy thiết kế **serialization/DTO** với chiến lược riêng cho tham chiếu ngược, danh tính, độ sâu và chu trình. `toString()` không nên được xem là serializer tổng quát.

## 5. Nếu bắt buộc in đồ thị: nhận diện đối tượng đã đi qua

Có tình huống chẩn đoán cần hiển thị nhiều tầng tham chiếu. Khi đó, `toString()` hoặc hàm hỗ trợ phải quản lý những đối tượng **đang nằm trên đường đệ quy hiện tại**.

Một cách hữu ích là `IdentityHashMap<Node, Boolean>`:

- `IdentityHashMap` so sánh khóa theo **danh tính tham chiếu** (`==`), không dựa vào `equals()`.
- Nếu đang duyệt một đối tượng rồi gặp lại **chính đối tượng ấy trên cùng đường gọi**, đã phát hiện chu trình.
- Thay vì gọi `toString()` lần nữa, hiển thị một ký hiệu ngắn như `Node(A, cycle)`.
- Gỡ đối tượng khỏi tập đường đi trong `finally` khi duyệt xong, kể cả nếu việc duyệt kết thúc bằng exception.

Tại sao cần so theo identity? Hai đối tượng khác nhau có thể `equals()` là `true` mà không tạo chu trình. Ngược lại, chính `equals()` hoặc `hashCode()` của đối tượng cũng có thể duyệt quan hệ hai chiều hoặc phụ thuộc dữ liệu mutable. Dùng `HashSet` làm tập phát hiện chu trình sẽ gọi các phương thức đó và có thể phát sinh lỗi khác.

Phân biệt hai chiến lược:

- **Active path (đường đệ quy hiện tại):** thêm khi đi vào, gỡ khi quay lui. Chỉ đánh dấu `cycle` khi gặp lại node trên đường đang duyệt. Một node được chia sẻ bởi hai nhánh khác nhau vẫn có thể xuất hiện ở cả hai nhánh.
- **Global visited (đã từng gặp ở bất kỳ nhánh nào):** đánh dấu lâu dài; thích hợp khi muốn không in lặp node, nhưng lần xuất hiện thứ hai của node chia sẻ chưa chắc tạo **chu trình**. Nếu dùng chiến lược này, hãy ghi rõ `already shown` thay vì tự động gọi đó là `cycle`.

Mỗi lần gọi `toString()` nên dùng một ngữ cảnh duyệt riêng; tránh một set dùng chung ở biến `static` cho mọi lời gọi, vì điều đó gây nhiễu giữa các lần in và giữa các thread.

## 6. Ví dụ Java 17 hoàn chỉnh: quan hệ hai chiều và đồ thị có chu trình

Chương trình dưới đây minh họa hai chiến lược an toàn:

1. `Department` và `Employee` chỉ trình bày ID/tóm tắt, nên không gọi `toString()` của nhau liên tục.
2. `Node` cho phép duyệt nhiều tầng liên kết; `IdentityHashMap` phát hiện node đang nằm trên đường duyệt để ngắt chu trình.

Tạo tệp **`ToStringCycleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public class ToStringCycleDemo {
    static final class Department {
        private final String code;
        private final List<Employee> employees = new ArrayList<>();

        Department(String code) {
            this.code = Objects.requireNonNull(code);
        }

        void add(Employee employee) {
            employees.add(Objects.requireNonNull(employee));
            employee.department = this;
        }

        @Override
        public String toString() {
            return "Department{code='" + code + "', employeeCount="
                    + employees.size() + "}";
        }
    }

    static final class Employee {
        private final String name;
        private Department department;

        Employee(String name) {
            this.name = Objects.requireNonNull(name);
        }

        @Override
        public String toString() {
            String departmentCode = department == null ? null : department.code;
            return "Employee{name='" + name + "', departmentCode='"
                    + departmentCode + "'}";
        }
    }

    static final class Node {
        private final String id;
        private final List<Node> links = new ArrayList<>();

        Node(String id) {
            this.id = Objects.requireNonNull(id);
        }

        void link(Node target) {
            links.add(Objects.requireNonNull(target));
        }

        @Override
        public String toString() {
            return render(this, new IdentityHashMap<>());
        }

        private static String render(Node current,
                IdentityHashMap<Node, Boolean> activePath) {
            if (activePath.containsKey(current)) {
                return "Node(" + current.id + ", cycle)";
            }
            activePath.put(current, Boolean.TRUE);
            try {
                StringJoiner children = new StringJoiner(", ");
                for (Node next : current.links) {
                    children.add(render(next, activePath));
                }
                return "Node(" + current.id + " -> [" + children + "])";
            } finally {
                activePath.remove(current);
            }
        }
    }

    public static void main(String[] args) {
        Department department = new Department("ENG");
        Employee an = new Employee("An");
        Employee binh = new Employee("Binh");
        department.add(an);
        department.add(binh);
        System.out.println(department);
        System.out.println(an);

        Node a = new Node("A");
        Node b = new Node("B");
        a.link(b);
        b.link(a);
        System.out.println(a);

        Node root = new Node("R");
        Node shared = new Node("S");
        root.link(shared);
        root.link(shared);
        System.out.println(root);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 ToStringCycleDemo.java
java ToStringCycleDemo
```

Stdout đã kiểm chứng bằng Java 17:

```text
Department{code='ENG', employeeCount=2}
Employee{name='An', departmentCode='ENG'}
Node(A -> [Node(B -> [Node(A, cycle)])])
Node(R -> [Node(S -> []), Node(S -> [])])
```

**Giải thích kết quả:**

1. `Department` biết hai nhân viên và mỗi nhân viên biết department; mặc dù tham chiếu là hai chiều, `Department.toString()` **chỉ in số lượng** và `Employee.toString()` **chỉ in mã**. Không có chuỗi gọi vòng.
2. Ở đồ thị `A → B → A`, khi `render` gặp A lần hai, A vẫn nằm trong `activePath`. Hàm trả `Node(A, cycle)` thay vì đệ quy thêm.
3. `R` liên kết tới **cùng một S hai lần**, nhưng S không trỏ về R và không nằm trên đường hiện tại sau khi kết thúc nhánh đầu. Vì mã dùng active path và gỡ node trong `finally`, S được in ở cả hai nhánh. Đây là **tham chiếu chia sẻ**, không phải chu trình.
4. `Node.toString()` khởi tạo bản đồ mới cho mỗi lần gọi, nên trạng thái theo dõi đường đi không rò sang một lần gọi độc lập khác.

Ví dụ này duyệt tuần tự một đồ thị không bị sửa đồng thời. Nếu có thread khác thêm/xóa liên kết khi đang in, cần chính sách snapshot hoặc đồng bộ phù hợp; `IdentityHashMap` riêng cho mỗi lời gọi không tự làm danh sách liên kết an toàn trước cập nhật đồng thời.

## 7. Giới hạn của giải pháp phát hiện chu trình

Phát hiện chu trình **không đồng nghĩa với loại bỏ mọi rủi ro đệ quy sâu**.

### 7.1. Đồ thị không có chu trình vẫn có thể rất sâu

Một chuỗi dài `A → B → C → ...` với hàng trăm nghìn node có thể làm stack tràn dù không hề gặp lại node nào. Nếu in đồ thị lớn hoặc do bên ngoài cung cấp, nên giới hạn:

- **Độ sâu tối đa**, ví dụ chỉ in 3–5 cấp liên kết;
- **số node/cạnh tối đa** được phép trình bày;
- **độ dài chuỗi tối đa**, tránh log quá lớn;
- hoặc dùng **thuật toán duyệt lặp** (stack/queue tường minh) khi thực sự cần biểu diễn đồ thị lớn.

Khi chạm giới hạn, đưa ký hiệu ngắn như `<max-depth>` hoặc `<truncated>` để người đọc hiểu rằng output đã được giới hạn. Không nên cắt chuỗi một cách âm thầm khiến nó trông như dữ liệu đầy đủ.

### 7.2. Tham chiếu được in bởi formatter khác

Bộ theo dõi `activePath` chỉ giúp các node được duyệt **thông qua cùng hàm `render`**. Nếu trong quá trình render bạn tự nối `+ someOtherObject`, Java có thể gọi `someOtherObject.toString()` bên ngoài cơ chế theo dõi hiện tại và tái tạo vòng lặp.

Nếu cần hiển thị nhiều kiểu đối tượng trong cùng đồ thị, nên dùng **một formatter có ngữ cảnh duyệt chung** truyền vào các hàm hỗ trợ, hoặc chọn biểu diễn nhận diện rút gọn cho những cạnh không duyệt tiếp. Một biến toàn cục duy nhất không phải lối tắt an toàn cho thiết kế này.

### 7.3. Hiệu năng và dữ liệu nhạy cảm

Một `toString()` quá sâu hoặc in toàn bộ collection lớn có thể tốn CPU, bộ nhớ và tạo log kích thước rất lớn. In cả đối tượng liên quan còn có nguy cơ vô tình đưa password, token, email hoặc thông tin cá nhân vào log. Thiết kế output nên **ngắn, có chủ đích và tránh trường nhạy cảm**, dù dữ liệu không chứa chu trình.

Với framework ORM, việc `toString()` đọc quan hệ lazy có thể kích hoạt tải dữ liệu ngoài dự kiến hoặc không truy cập được quan hệ nếu persistence context đã đóng. Giữ `toString()` theo ID và trường scalar thường vừa tránh vòng, vừa tránh tải thêm đồ thị quan hệ.

## 8. Các công cụ sinh `toString()` có tự tránh vòng không?

### 8.1. IDE sinh `toString()`

IDE có thể tự đưa các trường vào output theo lựa chọn của người dùng. Nếu chọn cả `department.employees` và `employee.department`, mã được sinh vẫn có thể đệ quy vô hạn. Hãy kiểm tra nội dung được sinh, nhất là các trường quan hệ object và collection.

### 8.2. Lombok `@ToString`

Nếu dùng Lombok, tính năng `@ToString` có thể đưa các field vào chuỗi; có thể sử dụng `@ToString.Exclude` để loại trừ phía tham chiếu ngược, hoặc `@ToString(onlyExplicitlyIncluded = true)` cùng `@ToString.Include` để chỉ cho phép những thuộc tính định danh cần thiết.

Ví dụ **đoạn cấu hình minh họa** (cần dependency Lombok, không thuộc tệp demo Java thuần ở trên):

```java
@ToString
class Employee {
    private String id;
    @ToString.Exclude
    private Department department;
}
```

Phần này minh họa hướng loại trừ, không phải chương trình chạy độc lập. Nếu nhiều lớp cùng dùng Lombok, cần rà soát **mọi cạnh quan hệ hai chiều**, đặc biệt khi thay đổi field sau này.

### 8.3. Java record

Record tạo `toString()` tự động từ các component. Điều đó tiện cho record chứa giá trị đơn giản như `String` hoặc `int`; nhưng record không làm các đối tượng tham chiếu bên trong trở nên bất biến sâu hay không có chu trình.

Nếu component là một graph object mà `toString()` của nó quay về record hoặc một nhánh tham chiếu cũ, vẫn có rủi ro. Có thể override `toString()` của record để chỉ in thông tin định danh phù hợp.

### 8.4. Array và collection helper

`Arrays.deepToString` có cơ chế xử lý một số tình huống mảng chứa tham chiếu vòng tới chính mảng/nhánh mảng đang duyệt, nhưng **không phải trình in chu trình tổng quát cho mọi object graph**. Một phần tử là POJO với `toString()` đi vòng qua quan hệ riêng vẫn có thể gây đệ quy.

Vì vậy đừng dùng một helper có chữ `deep` rồi suy luận rằng mọi tham chiếu hai chiều đều an toàn. Phải xác định rõ kiểu dữ liệu và ranh giới traversal.

## 9. Cách kiểm tra một `toString()` an toàn

Với một mô hình có quan hệ hai chiều, nên thử ít nhất các trường hợp:

1. **Đối tượng đơn lẻ:** object không có liên kết; kết quả ngắn và dễ hiểu.
2. **Quan hệ hai chiều đơn giản:** `Department → Employee → Department`; không xảy ra đệ quy vô hạn.
3. **Chu trình dài:** `A → B → C → A`; bộ phát hiện chu trình cắt đúng chỗ.
4. **Tự tham chiếu:** `A → A`; điều kiện dừng vẫn hoạt động.
5. **Tham chiếu chia sẻ nhưng không có vòng:** `R → S` qua hai cạnh; nếu dùng active path, không đánh dấu nhầm S là cycle.
6. **Đồ thị rỗng, phần tử null nếu mô hình cho phép:** không ném ngoại lệ do thiếu tham chiếu.
7. **Đồ thị rất sâu/rộng:** có giới hạn độ sâu và độ dài khi cần; không vô tình sinh log khổng lồ.
8. **Không lộ dữ liệu nhạy cảm:** kiểm tra output dự kiến và các field mới thêm.
9. **Tác động ORM:** nếu dùng quan hệ lazy, việc gọi `toString()` không bất ngờ làm tăng số truy vấn hoặc phụ thuộc phiên làm việc.

Ví dụ một phép kiểm tra hồi quy đặt trong code test Java sau khi tạo đồ thị `A → B → A`:

```java
String output = a.toString();
if (!output.contains("cycle")) {
    throw new AssertionError("Chu trinh chua duoc ngan");
}
```

Đây là **mảnh kiểm thử minh họa**, giả định biến `a` đã được tạo trong test. Kiểm tra còn nên xác nhận output thực tế khớp cấu trúc kỳ vọng. Không cố ý kích hoạt `StackOverflowError` trong test để chứng minh mã sai; thay bằng test các thiết kế an toàn và review đường gọi.

## 10. Câu hỏi thường gặp

### “Tôi chỉ cần in đối tượng cha, không gọi `child.toString()`, sao vẫn lỗi?”

Vì nối một collection vào chuỗi có thể khiến collection gọi `toString()` của từng phần tử. Đường gọi gián tiếp vẫn quay lại cha.

### “Bỏ `toString()` ở một phía có đủ không?”

Thường **đủ để cắt một vòng cụ thể** nếu phía còn lại chỉ in dữ liệu an toàn. Nhưng một đồ thị có nhiều đường liên kết có thể còn chu trình khác. Xem toàn bộ các cạnh mà formatter sẽ đi qua.

### “Dùng `HashSet` để ghi các object đã thăm được không?”

Có thể rủi ro khi `equals/hashCode` của chúng đệ quy theo quan hệ hoặc thay đổi. Với mục tiêu nhận biết **cùng instance đã nằm trên đường duyệt**, `IdentityHashMap` cho ngữ nghĩa phù hợp và rõ ràng hơn.

### “Nếu `toString()` gặp `null` thì sao?”

`String.valueOf(null)` tạo chuỗi `"null"`; nhưng gọi trực tiếp `null.toString()` là không hợp lệ. Trong formatter, kiểm tra `null` trước khi truy cập field hoặc đi tiếp qua liên kết.

### “Có nên trả về JSON từ `toString()`?”

Không bắt buộc và thường không phù hợp. `toString()` dành cho biểu diễn dễ đọc, chẩn đoán; trao đổi dữ liệu có schema và graph cycles cần serializer/DTO và cấu hình rõ ràng. Hãy chọn công cụ theo mục đích thay vì dựa vào một phương thức in đồ thị vô hạn.

## 11. Ghi nhớ

- Quan hệ hai chiều `A → B → A` là bình thường trong mô hình; **in cả hai phía trong `toString()`** có thể tạo vòng gọi vô hạn.
- Giải pháp đơn giản nhất là **in ID, scalar hoặc số lượng** ở một hay cả hai phía, thay vì in toàn bộ object liên kết.
- Nếu phải in nhiều tầng, theo dõi đường duyệt bằng **identity**, dừng khi gặp lại node đang active; phân biệt chu trình thật với node được chia sẻ.
- Tạo ngữ cảnh duyệt riêng cho mỗi lần gọi, dọn trong `finally`, và giới hạn độ sâu/kích thước đối với đồ thị lớn.
- Rà soát `toString()` do IDE, Lombok, record hoặc framework sinh ra; đừng mặc định chúng tự xử lý mọi vòng tham chiếu.
- Không dùng `StackOverflowError`, tăng stack hay log suppression như giải pháp gốc. Thiết kế đường duyệt và điều kiện dừng rõ ràng mới làm `toString()` an toàn.
