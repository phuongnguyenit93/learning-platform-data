# Sao chép nông và chia sẻ các đối tượng thành phần trong Java

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích thế nào là **shallow copy** (*sao chép nông*): tạo một object/collection/array bên ngoài mới nhưng những reference fields/phần tử tham chiếu vẫn có thể chỉ tới **chính các component objects cũ**.
- Phân biệt ba trường hợp **gán tham chiếu**, **sao chép nông** và **sao chép sâu theo nhu cầu** (*deep copy*), nhận diện object nào mới và object nào bị chia sẻ.
- Dự đoán ảnh hưởng của việc sửa outer object, thay reference của một field/phần tử và mutate trạng thái của object được chia sẻ.
- Hiểu ngữ nghĩa `Object.clone()`, interface `Cloneable`, `super.clone()` và vì sao clone mặc định về cơ bản là field-by-field shallow copy; nắm các hạn chế của `clone()`.
- Sử dụng copy constructor, static factory, `array.clone()`, `Arrays.copyOf`, `new ArrayList<>(...)`, `List.copyOf` và `Map.copyOf` mà không nhầm “container mới” với “mọi element cũng mới”.
- Phân biệt primitive elements với reference elements, một tầng copy với nested arrays, live unmodifiable views với snapshots.
- Nhận ra rằng các immutable components như `String` và immutable value records thường **có thể được chia sẻ an toàn**, không cần sao chép sâu không cần thiết.
- Thiết kế defensive copies khi nhận/trả mutable components, kiểm soát quyền sở hữu, tránh phá invariants và rò rỉ state qua aliases.
- Phân tích những tác động của shared mutable elements tới `equals`/`hashCode`, hash collections, multi-threaded access và vòng đời tài nguyên.
- Viết ví dụ Java 17+ độc lập, biên dịch/chạy, đọc stdout chính xác và kiểm thử identity lẫn value equality.

## 1. Tại sao cần hiểu reference trước khi nói “copy”?

Java variables có kiểu tham chiếu giữ **giá trị tham chiếu** tới object, không tự chứa nguyên một bản sao của object. Khi viết:

~~~java
Customer a = new Customer();
Customer b = a;
~~~

ta **không** tạo hai Customer objects. `a` và `b` cùng tham chiếu object đã tạo bởi một lần `new`. Bất kỳ method nào mutate object đó đều có thể được quan sát qua cả hai biến.

Sơ đồ:

~~~text
a --------+
          |
          v
    [Customer object]
          ^
          |
b --------+
~~~

Ngược lại, nếu tạo một Customer object mới nhưng chuyển **cùng reference Address** vào constructor, hai Customer objects là riêng biệt **nhưng Address object vẫn được chia sẻ**.

~~~text
a --> [Customer A] ----address----+
                                 |
                                 v
                              [Address]
                                 ^
                                 |
b --> [Customer B] ----address----+
~~~

Đây là tiền đề của shallow copy: **vỏ ngoài mới, các thành phần tham chiếu bên trong có thể vẫn là objects cũ**.

### 1.1. Gán reference không phải sao chép nông

Ba dòng cần phân biệt:

~~~java
Person b = a;                  // Cùng Person object, không copy.
Person c = new Person(a);      // Có thể copy nông/sâu tùy constructor.
Person d = a.copy();           // Phụ thuộc implementation của copy().
~~~

Không có quy tắc tên gọi `copy` hoặc constructor overload tự động tạo deep copy. **Phải đọc implementation và tài liệu hợp đồng**.

### 1.2. Sao chép nông là gì?

Với class:

~~~java
class Employee {
    String name;
    Address address;
}
~~~

Shallow copy thường sao chép giá trị các fields:

- `name`: String reference được sao chép, nhưng String immutable nên chia sẻ có thể an toàn.
- `address`: Address reference được sao chép; nếu Address mutable, hai Employee objects cùng nhìn một Address object.
- Primitive fields như `int age`: giá trị số được sao chép, nên thay `age` của copy không đổi `age` của gốc.

Không có chuyện **mọi referenced objects đều được sao chép mới** chỉ vì outer class tạo instance mới.

## 2. Chương trình đầu tiên: vỏ ngoài khác, Address bên trong giống

Lưu **`ShallowReferenceDemo.java`**:

~~~java
public class ShallowReferenceDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }

        void move(String nextCity) {
            city = nextCity;
        }
    }

    static final class Employee {
        String name;
        Address address;
        int score;

        Employee(String name, Address address, int score) {
            this.name = name;
            this.address = address;
            this.score = score;
        }

        Employee shallowCopy() {
            return new Employee(name, address, score);
        }
    }

    public static void main(String[] args) {
        Employee original = new Employee(
                "Lan", new Address("Ha Noi"), 10);
        Employee copy = original.shallowCopy();

        System.out.println("same outer=" + (original == copy));
        System.out.println("same address=" +
                (original.address == copy.address));

        copy.name = "Minh";
        copy.score = 20;
        System.out.println("original data=" +
                original.name + "," + original.score);
        System.out.println("copy data=" +
                copy.name + "," + copy.score);

        copy.address.move("Hue");
        System.out.println("original city=" +
                original.address.city());
        System.out.println("copy city=" + copy.address.city());
    }
}
~~~

Chạy:

~~~bash
javac ShallowReferenceDemo.java
java ShallowReferenceDemo
~~~

Stdout chính xác:

~~~text
same outer=false
same address=true
original data=Lan,10
copy data=Minh,20
original city=Hue
copy city=Hue
~~~

**Phân tích từng kết quả:**

1. `original != copy`: `shallowCopy()` gọi `new Employee(...)` nên có hai outer objects.
2. `original.address == copy.address`: constructor nhận và lưu **cùng giá trị reference Address**.
3. `copy.name = "Minh"` thay **reference field name trong copy**, không mutate original.name. String immutable càng giúp kết quả ổn định.
4. `copy.score = 20` thay **primitive field trong copy**, nên original.score giữ 10.
5. `copy.address.move("Hue")` mutate object Address chung, cả hai Employees nhìn Hue.

**Quy tắc ghi nhớ:** khi sao chép nông, **gán lại một reference field trong copy** khác với **mutate object mà reference field đang trỏ tới**.

## 3. So sánh ba mô hình bằng sơ đồ

### 3.1. Không copy: gán alias

~~~text
original -------------------+
                            v
                         [Person]
                            ^
alias ----------------------+

original == alias           true
original.address == alias.address  true nếu cùng field ở cùng object
~~~

### 3.2. Shallow copy: outer khác, child dùng chung

~~~text
original --> [Person 1] ---+
                          |
                          v
                        [Address]
                          ^
                          |
copy -----> [Person 2] ---+

original == copy           false
original.address == copy.address  true
~~~

### 3.3. Deep copy một tầng thành phần có chủ đích

~~~text
original --> [Person 1] --> [Address 1]
copy -----> [Person 2] --> [Address 2]

original == copy                  false
original.address == copy.address  false
~~~

Đây là “deep enough” cho mô hình Person→Address **nếu Address không giữ mutable nested references khác**. Nếu Address còn chứa `List<Coordinate>` mutable và copy constructor chỉ copy reference list, việc tách Address chưa đảm bảo toàn bộ graph độc lập.

### 3.4. Bảng dự đoán thay đổi

| Thao tác | Chỉ alias `b = a` | Shallow copy ngoài | Copy tách thành phần liên quan |
| --- | --- | --- | --- |
| `b.age = 20` với field primitive | Cùng outer object → a.age đổi | a.age không đổi | a.age không đổi |
| `b.address = new Address(...)` | a.address đổi do cùng outer | a.address giữ field reference cũ | a.address giữ field reference cũ |
| `b.address.setCity(...)` | a thấy đổi | a **có thể** thấy đổi nếu cùng Address | a không thấy đổi nếu Address riêng |
| Thay đổi một nested mutable list item | Có thể cùng object graph | Vẫn có thể thấy đổi | Tùy mức copy của nested item |
| Chi phí tạo objects | Không tạo thêm | Tạo ít nhất outer object | Có thể tạo outer + mutable child copies |

“Copy sâu” **không có độ sâu mặc định**: phải quyết định những thành phần nào được phép chia sẻ và những thành phần nào cần sở hữu độc lập.

## 4. Copy constructor có thể được viết để sao chép nông

Java **không tự cung cấp copy constructor** như một phép sao chép object mặc định. Một constructor do lập trình viên khai báo có thể sao chép từng field:

~~~java
class Invoice {
    private String number;
    private Customer customer;

    Invoice(Invoice source) {
        this.number = source.number;
        this.customer = source.customer;
    }
}
~~~

Đây là **mảnh code minh họa** trong ngữ cảnh có class `Customer` hợp lệ. `new Invoice(original)` tạo Invoice object mới, nhưng trường `customer` vẫn trỏ **cùng Customer** với original; vì vậy đây là *shallow copy*. Nếu Customer mutable, sửa Customer qua một Invoice có thể làm cả hai thay đổi theo cách quan sát được. Thí nghiệm Person–Address trước đó đã kiểm điều này bằng identity và mutation.

**Copy constructor không hứa deep copy chỉ nhờ tên gọi**. Nó có thể được thiết kế để validate, sao chép có chọn lọc, tính lại giá trị dẫn xuất hoặc trả lỗi; điều quan trọng là **hợp đồng** nó cung cấp. Khi mục tiêu chỉ là hiểu shallow-copy state sharing, không cần lặp thêm một chương trình copy constructor nhiều nhánh và một bài kiểm thử deep-copy ở đây.

## 5. `Object.clone()` là một đường khác có thể tạo bản sao nông

`Object.clone()` là method `protected`. Một class thông thường muốn dùng `super.clone()` theo convention cần `implements Cloneable`; `Cloneable` là **marker interface**, không tự khai báo một public `clone()`. Với implementation của `Object.clone()`, object mới được tạo theo cơ chế field-wise copy và **reference fields vẫn dùng chung nested objects**.

Phân biệt:

| Đường copy | Top-level object mới? | Child mutable có tách không? |
| --- | --- | --- |
| `b = a` | Không | Không |
| `new Invoice(a)` với constructor trên | Có | Không |
| `super.clone()` trên object Cloneable theo contract mặc định | Có | Không |
| Factory/copy constructor chuyên biệt | Tùy hợp đồng | Tùy hợp đồng |

`clone()` **không gọi constructor theo đường tạo object `new` thông thường**, nên invariants, `final` reference fields, tài nguyên và kế thừa có thể đòi xử lý đặc biệt. Ngoài ra, subclass có thể override `clone()` với chính sách khác; không suy mọi method mang tên `clone` đều shallow. Khi cần các điều kiện và so sánh chi tiết `Object.clone()`, hãy xét contract riêng của nó. Trọng tâm ở đây là: **root object có thể mới nhưng mutable children vẫn bị chia sẻ**.

## 6. Cẩn trọng khi clone một object có final reference field

Giả sử:

~~~java
class Folder {
    private final java.util.List<String> entries;

    Folder(java.util.List<String> entries) {
        this.entries = new java.util.ArrayList<>(entries);
    }
}
~~~

Nếu tự triển khai `clone()` bằng `super.clone()`, cloned Folder có field `entries` tham chiếu cùng mutable list. Vì field `final`, bình thường không thể gán lại nó bằng một mutable list copy trong ordinary Java code của clone method.

Đây là một lý do nên ưu tiên **copy constructor hoặc static factory** thay vì ép một class có final mutable-reference field đi qua `Object.clone`. Không dùng reflection để lách field final nhằm sửa một thiết kế cloning.

Nếu list chứa toàn `String` và được lưu thành unmodifiable snapshot thực sự, chia sẻ cấu trúc ấy có thể đã an toàn; quyết định dựa trên ownership và mutability, không dựa trên thói quen “clone tất cả”.

## 7. Array: `clone()` tạo array mới, nhưng elements có thể shared

Mọi Java array có hỗ trợ `clone()`, trả array object mới có cùng length và component type tương ứng. Từ góc độ elements:

- Primitive array: từng primitive value được copy.
- Reference array: từng **reference value** được copy; element objects không được clone tự động.
- Nested arrays: array ngoài được clone, các subarrays vẫn là objects cũ nếu không copy riêng.

### 7.1. Primitive array

~~~java
int[] original = {1, 2, 3};
int[] copy = original.clone();

copy[0] = 9;
// original[0] vẫn 1.
~~~

Vì array component type là `int`, copy các phần tử đã tách values. Với primitive-only arrays, một tầng clone thường đủ để ngăn mutation của một array ảnh hưởng array còn lại.

### 7.2. Reference array

~~~java
Customer[] original = {someCustomer};
Customer[] copy = original.clone();

boolean sameArray = original == copy;           // false.
boolean sameItem = original[0] == copy[0];      // true.
~~~

Ở đây `Customer` và `someCustomer` là mảnh minh họa cần khai báo. Việc gán `copy[0] = new Customer(...)` thay element reference trong copy, không thay `original[0]`. Nhưng gọi `copy[0].setName(...)` trước khi thay element sẽ mutate object Customer mà original vẫn trỏ.

## 8. Demo array primitive và reference elements

Lưu **`ArrayShallowCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayShallowCopyDemo {
    static final class Cell {
        int value;

        Cell(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2};
        int[] numberCopy = numbers.clone();
        numberCopy[0] = 9;

        System.out.println("int same array=" +
                (numbers == numberCopy));
        System.out.println("original int=" + numbers[0]);
        System.out.println("copied int=" + numberCopy[0]);

        Cell[] cells = {new Cell(5), new Cell(6)};
        Cell[] cellCopy = cells.clone();

        System.out.println("cell same array=" +
                (cells == cellCopy));
        System.out.println("cell same first object=" +
                (cells[0] == cellCopy[0]));

        cellCopy[0].value = 50;
        cellCopy[1] = new Cell(60);

        System.out.println("original contents=" +
                cells[0].value + "," + cells[1].value);
        System.out.println("copy contents=" +
                cellCopy[0].value + "," + cellCopy[1].value);
        System.out.println("primitive copy=" +
                Arrays.toString(numberCopy));
    }
}
~~~

Chạy:

~~~bash
javac ArrayShallowCopyDemo.java
java ArrayShallowCopyDemo
~~~

Output:

~~~text
int same array=false
original int=1
copied int=9
cell same array=false
cell same first object=true
original contents=50,6
copy contents=50,60
primitive copy=[9, 2]
~~~

**Hai mutation khác nhau:**

- `cellCopy[0].value = 50` sửa Cell object **dùng chung**, original nhìn thấy 50.
- `cellCopy[1] = new Cell(60)` thay reference **trong array copy**; original giữ reference tới Cell(6) cũ.

Không nên suy luận “vì array đã clone nên mỗi object trong array cũng clone”.

### 8.1. `Arrays.copyOf` thì sao?

`Arrays.copyOf(source, source.length)` cũng tạo array mới và sao chép các phần tử. Với reference array, elements references vẫn shared. Nó còn cho phép chọn length khác; phần kéo dài được điền default values thích hợp. Không tự tạo copies của từng referenced object.

## 9. Mảng hai chiều: copy hàng ngoài vẫn giữ subarrays

Với:

~~~java
int[][] matrix = {{1, 2}, {3, 4}};
int[][] shallow = matrix.clone();
~~~

`matrix != shallow`, nhưng `matrix[0] == shallow[0]` vì **int[] hàng thứ nhất** được chia sẻ. `shallow[0][0] = 99` làm `matrix[0][0]` đổi.

Muốn tách các hàng:

~~~java
int[][] separate = matrix.clone();
for (int i = 0; i < separate.length; i++) {
    separate[i] = matrix[i].clone();
}
~~~

Đây là copy ở hai tầng cho graph dạng int[][] không chứa self-references. Với object elements mutable còn cần xem xét sâu hơn.

### 9.1. Chương trình runnable

Lưu **`MatrixCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class MatrixCopyDemo {
    static int[][] copyRows(int[][] source) {
        int[][] result = source.clone();
        for (int i = 0; i < result.length; i++) {
            result[i] = source[i].clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] first = {{1, 2}, {3, 4}};
        int[][] shallow = first.clone();
        int[][] separate = copyRows(first);

        System.out.println("outer shared=" + (first == shallow));
        System.out.println("row shared=" +
                (first[0] == shallow[0]));
        System.out.println("deep row shared=" +
                (first[0] == separate[0]));

        shallow[0][0] = 9;

        System.out.println("original row=" +
                Arrays.toString(first[0]));
        System.out.println("shallow row=" +
                Arrays.toString(shallow[0]));
        System.out.println("separate row=" +
                Arrays.toString(separate[0]));
    }
}
~~~

Chạy:

~~~bash
javac MatrixCopyDemo.java
java MatrixCopyDemo
~~~

Output:

~~~text
outer shared=false
row shared=true
deep row shared=false
original row=[9, 2]
shallow row=[9, 2]
separate row=[1, 2]
~~~

Với `int[][]`, mỗi subarray chứa primitive numbers nên clone từng subarray đủ cho độc lập nội dung. Nếu hàng null, `source[i].clone()` sẽ gây NPE; phương thức ở đây giả định mọi hàng non-null và cần thêm validation nếu dùng API tổng quát.

## 10. Collection copy: `new ArrayList<>(source)`

Khi viết:

~~~java
List<Employee> copy = new ArrayList<>(original);
~~~

`copy` là **List object mới** với element references được sao chép theo iteration/order của source. Nó **không gọi `new Employee` cho từng phần tử**.

Hệ quả:

- `copy.add(newEmployee)` thay cấu trúc copy, không tự thay original.
- `copy.remove(0)` bỏ reference trong copy, original list vẫn giữ reference cũ.
- `copy.get(0).setName(...)` mutate Employee object **được dùng chung**, cả hai lists có thể thấy tên mới.

### 10.1. Chương trình runnable

Lưu **`ListShallowCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListShallowCopyDemo {
    static final class Item {
        private String name;

        Item(String name) {
            this.name = name;
        }

        void rename(String next) {
            name = next;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        List<Item> original = new ArrayList<>();
        original.add(new Item("A"));

        List<Item> copy = new ArrayList<>(original);

        System.out.println("same list=" + (original == copy));
        System.out.println("same item=" +
                (original.get(0) == copy.get(0)));

        copy.get(0).rename("X");
        copy.add(new Item("B"));

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);

        copy.set(0, new Item("Y"));
        System.out.println("after replace original=" + original);
        System.out.println("after replace copy=" + copy);
    }
}
~~~

Chạy:

~~~bash
javac ListShallowCopyDemo.java
java ListShallowCopyDemo
~~~

Output:

~~~text
same list=false
same item=true
original=[X]
copy=[X, B]
after replace original=[X]
after replace copy=[Y, B]
~~~

**Giải thích:**

- Cả hai lists ban đầu cùng giữ Item A.
- `rename("X")` sửa Item chung → cả hai lists in X.
- `copy.add(B)` chỉ làm copy list dài hơn.
- `copy.set(0,new Item("Y"))` thay reference tại vị trí 0 trong copy; original vẫn giữ Item X.

Đây là ví dụ cần hiểu trước khi dùng các collection APIs sao chép.

## 11. `List.copyOf`: snapshot cấu trúc nhưng không clone element objects

`List.copyOf(source)` trả **unmodifiable List** theo nội dung/cấu trúc tại thời điểm tạo (trong trường hợp source mutable thông thường), nhưng references tới mutable elements vẫn có thể shared.

Cần tách hai mức:

1. **Cấu trúc collection:** thêm/xóa/set không được phép qua unmodifiable list.
2. **State của element object:** nếu element mutable và alias khác có thể sửa, việc đọc qua snapshot có thể thấy giá trị mới.

### 11.1. Demo snapshot và component alias

Lưu **`ListSnapshotSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListSnapshotSharingDemo {
    static final class Entry {
        String value;

        Entry(String value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public static void main(String[] args) {
        Entry shared = new Entry("old");
        List<Entry> source = new ArrayList<>();
        source.add(shared);

        List<Entry> snapshot = List.copyOf(source);

        source.add(new Entry("second"));
        System.out.println("source size=" + source.size());
        System.out.println("snapshot size=" + snapshot.size());

        shared.value = "new";
        System.out.println("snapshot first=" + snapshot.get(0));

        try {
            snapshot.add(new Entry("third"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }
    }
}
~~~

Chạy:

~~~bash
javac ListSnapshotSharingDemo.java
java ListSnapshotSharingDemo
~~~

Output:

~~~text
source size=2
snapshot size=1
snapshot first=new
snapshot cannot add
~~~

Snapshot không nhận entry second thêm sau đó, nhưng thành phần shared đổi từ old thành new.

**Đừng nói `List.copyOf` tạo deep immutable object graph** khi các elements có setters hoặc lộ mutable nested references.

### 11.2. Null và việc tái sử dụng instance

`List.copyOf` không cho elements null theo API. Nếu input vốn là unmodifiable list thích hợp, implementation **có thể tái sử dụng list instance** thay vì nhất thiết cấp phát một outer list mới. Vì vậy không dùng `List.copyOf(source) != source` như assertion phổ quát của Java.

Nếu yêu cầu bắt buộc **list object identity mới**, hãy chọn construction API có contract phù hợp và vẫn xem semantics của elements. Thông thường yêu cầu nghiệp vụ cần **snapshot/unmodifiable** chứ không cần khác identity bằng mọi giá.

## 12. `Collections.unmodifiableList` có thể chỉ là view

Khác với việc copy một list mới, `Collections.unmodifiableList(source)` tạo **unmodifiable view** của backing list:

- Caller không sửa cấu trúc qua view.
- Nếu code khác còn giữ `source` mutable và sửa nó, view phản ánh thay đổi.
- Element references vẫn chia sẻ.
- View không phải “deep copy” hoặc “snapshot đã đóng băng”.

### 12.1. Chương trình đối chiếu view và list copy

Lưu **`ViewVsCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> mutableCopy = new ArrayList<>(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("mutable copy=" + mutableCopy);
        System.out.println("snapshot=" + snapshot);

        mutableCopy.add("C");
        System.out.println("copy after add=" + mutableCopy);

        try {
            view.add("D");
        } catch (UnsupportedOperationException expected) {
            System.out.println("view cannot add");
        }
    }
}
~~~

Chạy:

~~~bash
javac ViewVsCopyDemo.java
java ViewVsCopyDemo
~~~

Output:

~~~text
source=[A, B]
view=[A, B]
mutable copy=[A]
snapshot=[A]
copy after add=[A, C]
view cannot add
~~~

Ở đây elements là immutable `String`, nên ta chỉ thấy khác biệt ở **cấu trúc lists**. Với mutable element objects, cả view, mutableCopy và snapshot ban đầu có thể chia sẻ các elements tương ứng.

## 13. `Map.copyOf` và map copy constructors cũng là copy nông về values

Tương tự, một `HashMap<>(sourceMap)` tạo map mới chứa entries/keys/values references tương ứng. `Map.copyOf(sourceMap)` tạo unmodifiable map với entries ở thời điểm copy nhưng không deep-copy mutable values.

Lưu **`MapShallowCopyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapShallowCopyDemo {
    static final class Setting {
        String text;

        Setting(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        Setting value = new Setting("light");
        Map<String, Setting> original = new HashMap<>();
        original.put("theme", value);

        Map<String, Setting> copy = new HashMap<>(original);
        Map<String, Setting> snapshot = Map.copyOf(original);

        System.out.println("same map=" + (original == copy));
        System.out.println("same value=" +
                (original.get("theme") == copy.get("theme")));

        value.text = "dark";
        System.out.println("original theme=" +
                original.get("theme").text);
        System.out.println("copy theme=" +
                copy.get("theme").text);
        System.out.println("snapshot theme=" +
                snapshot.get("theme").text);

        copy.put("size", new Setting("large"));
        System.out.println("original entries=" + original.size());
        System.out.println("copy entries=" + copy.size());
    }
}
~~~

Chạy:

~~~bash
javac MapShallowCopyDemo.java
java MapShallowCopyDemo
~~~

Output:

~~~text
same map=false
same value=true
original theme=dark
copy theme=dark
snapshot theme=dark
original entries=1
copy entries=2
~~~

**Chú ý thêm về keys:** Nếu key là mutable object và `equals`/`hashCode` phụ thuộc mutable fields, cả original và shallow-copied maps có thể gặp rủi ro lookup sau mutation. `Map.copyOf` không tự biến mutable keys/values thành immutable values.

Với Map-copy APIs cần xét null policy: `Map.copyOf` không chấp nhận null keys/values; không nên áp dụng nó thay `new HashMap<>(source)` mà không xét input contract.

## 14. Có khi nào chia sẻ elements là tốt?

Có. Với **immutable components**, copy reference là an toàn về mutation state.

Ví dụ `record Coordinate(int x,int y)`, hoặc `String`, `LocalDate`, `BigDecimal` với immutable value semantics. Hai copied containers có thể dùng chung immutable Coordinate object mà không lo Coordinate bị chỉnh tại chỗ.

### 14.1. Demo phần tử bất biến và các container độc lập

Lưu **`ImmutableComponentSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableComponentSharingDemo {
    record Coordinate(int x, int y) {
    }

    public static void main(String[] args) {
        Coordinate point = new Coordinate(1, 2);
        List<Coordinate> original = new ArrayList<>();
        original.add(point);

        List<Coordinate> copy = new ArrayList<>(original);

        System.out.println("same list=" + (original == copy));
        System.out.println("same point=" +
                (original.get(0) == copy.get(0)));

        Coordinate moved = new Coordinate(9, 2);
        copy.set(0, moved);

        System.out.println("original point=" + original.get(0));
        System.out.println("copy point=" + copy.get(0));
        System.out.println("old point=" + point);
    }
}
~~~

Chạy:

~~~bash
javac ImmutableComponentSharingDemo.java
java ImmutableComponentSharingDemo
~~~

Output:

~~~text
same list=false
same point=true
original point=Coordinate[x=1, y=2]
copy point=Coordinate[x=9, y=2]
old point=Coordinate[x=1, y=2]
~~~

**Diễn giải:**

- Ban đầu hai lists giữ cùng immutable Coordinate instance.
- Không tồn tại operation thay `x` trên chính record point.
- `copy.set(0,moved)` chỉ đổi reference trong copy list, original vẫn giữ point cũ.
- Đây là trường hợp shallow copying **đủ và có lợi**: không cần deep-copy mỗi Coordinate.

**Lưu ý:** nếu record chứa `int[]` hoặc mutable List elements, hãy kiểm tra sâu hơn; từ khóa record một mình không deep-immutable.

## 15. Defensive copying ở cả input và output boundaries

Một vấn đề khác: class không phải là bản copy, nhưng muốn **bảo vệ state nội bộ** khỏi aliases bên ngoài. Khi constructor nhận mutable object và giữ reference trực tiếp, client có thể mutate state nội bộ từ outside. Khi getter trả mutable field trực tiếp, client lại có một alias.

### 15.1. Anti-pattern

~~~java
class BadStore {
    private final int[] data;

    BadStore(int[] data) {
        this.data = data; // Nhận nguyên alias input.
    }

    int[] getData() {
        return data; // Lộ alias output.
    }
}
~~~

`final` không bảo vệ array elements. Vì vậy caller có thể sửa `input[0]` hoặc `store.getData()[0]`.

### 15.2. Chương trình defensive copy đúng cho primitive array

Lưu **`DefensiveArrayCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class DefensiveArrayCopyDemo {
    static final class Values {
        private final int[] data;

        Values(int[] input) {
            data = input.clone();
        }

        int[] copyValues() {
            return data.clone();
        }

        int sum() {
            return Arrays.stream(data).sum();
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2, 3};
        Values values = new Values(input);

        input[0] = 99;
        int[] retrieved = values.copyValues();
        retrieved[1] = 88;

        System.out.println("input first=" + input[0]);
        System.out.println("retrieved second=" + retrieved[1]);
        System.out.println("stored sum=" + values.sum());
    }
}
~~~

Chạy:

~~~bash
javac DefensiveArrayCopyDemo.java
java DefensiveArrayCopyDemo
~~~

Output:

~~~text
input first=99
retrieved second=88
stored sum=6
~~~

Vì `int[]` chứa primitive values, clone input/output đủ để tách quyền sửa các phần tử ở ví dụ này.

### 15.3. Khi components còn mutable references

Nếu field là `List<MutableAddress>`, gọi `List.copyOf` giúp tách cấu trúc list, nhưng mỗi MutableAddress vẫn có thể được sửa qua alias. Muốn độc lập thực sự, hãy:

1. Dùng **immutable Address value type**, hoặc
2. Copy các Address objects sang một representation private và ngăn getter lộ mutable references, hoặc
3. Định nghĩa rõ rằng API **cho phép shared ownership/mutation** (đây là contract khác với snapshot độc lập).

Không có hướng duy nhất hợp lệ cho mọi domain; quan trọng là client hiểu semantics.

## 16. Deep copy ở mức phù hợp, không phải sao chép vô hạn

Ví dụ một `Document` giữ list paragraphs, mỗi paragraph giữ text String immutable. Muốn snapshot độc lập khỏi list mutable:

- Tạo outer Document object mới.
- Tạo list structure mới/unmodifiable snapshot.
- Chia sẻ **immutable String values** bên trong.

Không cần làm `new String(existingString)` để “sâu hơn”. Những copies ấy không làm String an toàn hơn về mutation.

Nếu mỗi paragraph là MutableParagraph với method `setText`, bản copy cần tự tạo paragraph objects mới hoặc chuyển thành immutable Paragraph value.

### 16.1. Demo copy list mutable elements sang immutable snapshots

Lưu **`SelectiveDeepCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SelectiveDeepCopyDemo {
    static final class MutableLine {
        private String text;

        MutableLine(String text) {
            this.text = text;
        }

        void replace(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    record LineSnapshot(String text) {
    }

    static final class Report {
        private final List<LineSnapshot> lines;

        Report(List<MutableLine> source) {
            List<LineSnapshot> values = new ArrayList<>();
            for (MutableLine line : source) {
                values.add(new LineSnapshot(line.text()));
            }
            lines = List.copyOf(values);
        }

        List<LineSnapshot> lines() {
            return lines;
        }
    }

    public static void main(String[] args) {
        MutableLine first = new MutableLine("old");
        List<MutableLine> draft = new ArrayList<>();
        draft.add(first);

        Report report = new Report(draft);
        first.replace("new");
        draft.add(new MutableLine("extra"));

        System.out.println("draft first=" + first.text());
        System.out.println("draft size=" + draft.size());
        System.out.println("report first=" +
                report.lines().get(0).text());
        System.out.println("report size=" + report.lines().size());
    }
}
~~~

Chạy:

~~~bash
javac SelectiveDeepCopyDemo.java
java SelectiveDeepCopyDemo
~~~

Output:

~~~text
draft first=new
draft size=2
report first=old
report size=1
~~~

**Ý nghĩa:** Report sao chép **các giá trị văn bản cần giữ** từ mutable inputs sang immutable LineSnapshot records, rồi tạo unmodifiable list. Nó không cố clone mọi object trong hệ thống. Đây là cách deep-copy **đúng ranh giới dữ liệu**.

Nếu `MutableLine.text()` có thể thay đổi đồng thời trong thread khác, snapshot cần một consistency contract phù hợp; chỉ copy không tự tạo atomic snapshot của shared mutable state.

## 17. Shallow copy trong record và copy factory

Record constructor chỉ nhận/ghi các component values. Một factory tự xây record mới bằng các accessors của record cũ có thể tạo outer record khác nhưng giữ cùng mutable component reference.

### 17.1. Demo record copy nông

Lưu **`RecordShallowCopyDemo.java`**:

~~~java
public class RecordShallowCopyDemo {
    record Picture(String title, int[] pixels) {
    }

    public static void main(String[] args) {
        Picture first = new Picture("A", new int[] {1, 2});
        Picture second = new Picture(
                first.title(), first.pixels());

        System.out.println("same record=" + (first == second));
        System.out.println("same pixels=" +
                (first.pixels() == second.pixels()));

        second.pixels()[0] = 9;

        System.out.println("first pixel=" + first.pixels()[0]);
        System.out.println("second pixel=" + second.pixels()[0]);
        System.out.println("records equal=" + first.equals(second));
    }
}
~~~

Chạy:

~~~bash
javac RecordShallowCopyDemo.java
java RecordShallowCopyDemo
~~~

Output:

~~~text
same record=false
same pixels=true
first pixel=9
second pixel=9
records equal=true
~~~

Hai record instances có identity riêng nhưng cả hai cùng lưu reference tới pixel array và cùng String title. Generated record equality dựa trên component values; với array component, equality kiểm tra **array identity**, nên hai records này equal. Sửa array qua reference trong record thứ hai cũng tác động array của record thứ nhất. Nếu muốn độc lập pixels, constructor/accessor cần defensive-copy; nếu muốn equality theo nội dung pixels, tự triển khai equals/hashCode với Arrays.equals/Arrays.hashCode.

Không nhầm record component **reference equality** với record outer **identity equality**. Các generated methods có semantics value/component-oriented; với array components nó không tự compare contents, nhưng cùng array reference thì component bằng nhau.

Nếu muốn Picture có **independent pixel data**, constructor phải clone input và accessor trả copy, và nếu muốn equality theo pixel contents thì override `equals`/`hashCode` nhất quán.

## 18. Bản sao nông không “khóa” quyền sửa của người sở hữu cũ

Một nguyên tắc ownership rất quan trọng:

> Nếu một object mutable còn được tham chiếu ở hai nơi, cả hai nơi đều có khả năng ảnh hưởng nhau qua API mutate của object ấy.

Ví dụ copy một shopping cart structure nhưng giữ các Product objects mutable. Khi một Product bị đổi giá, cả hai cart copies có thể tính tổng theo giá mới dù danh sách items độc lập.

Đôi khi đó là **ý định có chủ đích**: cả hai carts cần nhìn cùng live Product catalog entry. Nhưng nếu mục tiêu là “báo giá tại lúc đặt hàng”, nên snapshot giá vào immutable `OrderLine` riêng, không giữ reference tới mutable Product.price để tính lại hóa đơn cũ.

### 18.1. Các contract thường gặp

- **Live shared reference:** nhiều views cố ý cùng nhìn state hiện tại; mọi mutation được quan sát.
- **Shallow snapshot:** tập references được chụp ở thời điểm T, nhưng referenced objects có thể đổi state.
- **Value snapshot:** cả những giá trị nghiệp vụ cần giữ đều được copy/đóng băng.
- **Deep clone of owned graph:** tạo bản sao các mutable objects thuộc quyền sở hữu, giữ riêng và duy trì alias/cycle invariants khi cần.

Nếu API chỉ ghi “copy” mà không giải thích loại copy, người dùng rất dễ hiểu sai.

## 19. Copy nông và `equals`/`hashCode`

Shallow copy không bảo đảm:

- `original.equals(copy)` true. Điều đó tùy **định nghĩa equality** của class.
- `original.hashCode() == copy.hashCode()` nếu class dùng Object.identity semantics; nếu chúng được coi equal theo `equals` thì hợp đồng Java đòi hashes bằng nhau.
- `original == copy` true; copy constructor/clone thông thường tạo outer object mới.
- Các hash codes là stable trong trường hợp mutable fields/children tham gia equality/hash.

### 19.1. Mutable shared key nguy hiểm

Nếu hai shallow copies đều dùng chung một mutable key object đã đưa vào `HashMap`, sửa field tham gia `hashCode()` của key qua một alias có thể khiến lookup thất bại. Việc có hai map/list outer copies **không sửa** rủi ro này.

Giải pháp: chọn immutable key/ID ổn định, hoặc sao chép key value thành immutable representation trước khi lưu.

### 19.2. Nếu child immutable thì sao?

Nếu field là immutable `record Key(String id)` và cả hai outer copies chia sẻ Key reference, equality/hash không bị thay vì mutation. Không cần clone Key để có cùng semantics.

## 20. Shallow copy với đồ thị có vòng và nhiều aliases

Trong object graph phức tạp:

~~~text
A.child ----> C
B.child ----> C

C.parent? --> A
~~~

Sao chép nông A thành A2 thường sao chép reference `A.child` tới **chính C**. Nếu C có field `parent` trỏ A, A2 và C không tự trở thành một đồ thị hai chiều “đã copy” nhất quán.

Điều này quan trọng với:

- Parent–child backlinks.
- Doubly linked lists.
- Graph nodes có `prev`/`next`.
- Mutable aggregate roots với children giữ pointer về owner.
- Shared entities tham gia nhiều aggregates.

Một deep copy graph đúng cần quyết định xem:

1. Copy những nodes nào?
2. Nodes shared ở gốc có tiếp tục được shared trong bản copy không?
3. Back references trỏ về owner mới hay cũ?
4. Có cycles không?
5. Có cần giữ invariant “hai edges trỏ cùng object” trong copied graph không?

### 20.1. Ví dụ chứng minh backlink không tự đổi

Lưu **`GraphShallowCopyDemo.java`**:

~~~java
public class GraphShallowCopyDemo {
    static final class Parent {
        String name;
        Child child;

        Parent(String name) {
            this.name = name;
        }

        Parent(Parent source) {
            this.name = source.name;
            this.child = source.child;
        }
    }

    static final class Child {
        Parent parent;
        String label;

        Child(String label, Parent parent) {
            this.label = label;
            this.parent = parent;
        }
    }

    public static void main(String[] args) {
        Parent original = new Parent("A");
        Child child = new Child("child", original);
        original.child = child;

        Parent copy = new Parent(original);

        System.out.println("same parent=" + (original == copy));
        System.out.println("same child=" +
                (original.child == copy.child));
        System.out.println("child points original=" +
                (copy.child.parent == original));
        System.out.println("child points copy=" +
                (copy.child.parent == copy));
    }
}
~~~

Chạy:

~~~bash
javac GraphShallowCopyDemo.java
java GraphShallowCopyDemo
~~~

Output:

~~~text
same parent=false
same child=true
child points original=true
child points copy=false
~~~

Đây **không phải bug của Java cloning** mà là hệ quả tất yếu của việc chỉ copy outer reference fields. Nếu ứng dụng yêu cầu backlink theo parent mới, cần xây bản sao graph riêng và cập nhật links một cách nhất quán.

### 20.2. Deep-copy graph không phải cứ gọi clone() đệ quy

Một cách clone đệ quy ngây thơ có thể lặp vô hạn với cycles hoặc tạo nhiều bản sao khác nhau của một node vốn shared. Với graph general-purpose, thường cần **identity-based map original→copy**, đặt copy vào map trước khi copy references, rồi dựng edges để giữ sharing/cycles theo yêu cầu.

Không cần triển khai thuật toán graph cloning phức tạp cho bài này, nhưng cần hiểu vì sao “copy nông” đơn giản và “copy sâu” phụ thuộc toàn bộ graph semantics.

## 21. Shared mutable components với nhiều threads

Một outer copy mới **không** tự tách khả năng truy cập đồng thời tới nested mutable child. Nếu Thread A sửa `copy.child.count` và Thread B đọc `original.child.count`, hai threads vẫn đang truy cập **cùng object Child**, có thể phát sinh data race nếu không có synchronization thích hợp.

### 21.1. Snapshot outer không có nghĩa component thread-safe

~~~java
class Holder {
    final MutableCounter counter;

    Holder(MutableCounter counter) {
        this.counter = counter;
    }

    Holder copy() {
        return new Holder(counter);
    }
}
~~~

Đây là mảnh minh họa cần `MutableCounter` phù hợp. Hai Holder objects giữ một Counter reference. `final` giúp cố định reference, **không** làm Counter thread-safe.

Nếu component phải chia sẻ live state, dùng loại thread-safe phù hợp (ví dụ `AtomicInteger` với counter đơn giản), locks/ownership và rules publication đúng. Nếu cần snapshot **không đổi**, sao chép **giá trị counter** sang immutable primitive/record thay vì giữ AtomicInteger live reference.

### 21.2. Demo phân biệt shared counter và snapshot value

Lưu **`SharedComponentCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SharedComponentCounterDemo {
    static final class View {
        final AtomicInteger counter;

        View(AtomicInteger counter) {
            this.counter = counter;
        }

        View shallowCopy() {
            return new View(counter);
        }
    }

    record Snapshot(int count) {
    }

    public static void main(String[] args) {
        AtomicInteger shared = new AtomicInteger(5);
        View first = new View(shared);
        View second = first.shallowCopy();

        Snapshot snapshot = new Snapshot(shared.get());

        System.out.println("same counter=" +
                (first.counter == second.counter));
        System.out.println("snapshot before=" + snapshot.count());

        second.counter.incrementAndGet();

        System.out.println("first count=" + first.counter.get());
        System.out.println("second count=" + second.counter.get());
        System.out.println("snapshot after=" + snapshot.count());
    }
}
~~~

Chạy:

~~~bash
javac SharedComponentCounterDemo.java
java SharedComponentCounterDemo
~~~

Output:

~~~text
same counter=true
snapshot before=5
first count=6
second count=6
snapshot after=5
~~~

`AtomicInteger` là một shared mutable object có atomic operations cho use case counter. Nó **không phải immutable**, còn `Snapshot` là immutable record giữ primitive value tại thời điểm tạo.

**Lưu ý:** thread safety của AtomicInteger không biến mọi invariant nhiều fields/counters thành atomic transaction. Nếu business logic cần cập nhật nhiều resources đồng thời, cần coordination riêng.

## 22. Sao chép object có tài nguyên ngoài JVM heap

Các objects như `Socket`, `InputStream`, database `Connection`, file handles hay executors không phải các value objects có thể deep-copy tùy ý.

Nếu một shallow copy của wrapper giữ cùng reference tới `AutoCloseable` resource:

- Cả hai wrappers có thể đang dùng **cùng resource**.
- Một wrapper `close()` resource khiến wrapper còn lại không dùng được như trước.
- Nếu cả hai cùng nghĩ mình là owner, có thể đóng hai lần hoặc quản lý lifecycle sai.
- Clone một connection không có nghĩa tự tạo một independent network/database connection.

### 22.1. Demo ownership của shared closeable

Lưu **`SharedResourceCopyDemo.java`**:

~~~java
public class SharedResourceCopyDemo {
    static final class Resource implements AutoCloseable {
        private boolean closed;

        String read() {
            return closed ? "closed" : "open";
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    static final class Reader {
        private final Resource resource;

        Reader(Resource resource) {
            this.resource = resource;
        }

        Reader(Reader source) {
            this.resource = source.resource;
        }

        String status() {
            return resource.read();
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();
        Reader first = new Reader(resource);
        Reader second = new Reader(first);

        System.out.println("before first=" + first.status());
        System.out.println("before second=" + second.status());

        resource.close();

        System.out.println("after first=" + first.status());
        System.out.println("after second=" + second.status());
    }
}
~~~

Chạy:

~~~bash
javac SharedResourceCopyDemo.java
java SharedResourceCopyDemo
~~~

Output:

~~~text
before first=open
before second=open
after first=closed
after second=closed
~~~

**Đây là resource mô phỏng**, không phải file thật. Nó làm rõ sharing một closeable reference. Trong hệ thống thực, ownership của resource cần được thiết kế rõ: ai tạo, ai được mượn dùng, ai close, close có idempotent không, và copy wrapper có được phép không.

## 23. Tại sao serialization không phải phép deep copy mặc định?

Một số code sao chép object bằng cách serialize rồi deserialize, hoặc chuyển qua JSON và đọc lại. Không nên coi đó là cơ chế “deep clone cho mọi object” mặc định:

- Không phải mọi types serializable.
- Transient fields, custom serialization, class versions và security policies ảnh hưởng kết quả.
- Objects như active connections, threads, locks hoặc native handles không có value-copy semantics.
- JSON có thể làm mất type identity, cycles và shared references tùy codec/configuration.
- Serialization có chi phí I/O/CPU và nguy cơ an toàn với untrusted input.

Nếu mục tiêu là copy vài fields và mutable components đơn giản, copy constructor/static factory thường rõ hơn.

Nếu cần deep-copy một object graph phức tạp với cycles, nên chọn một mô hình snapshot/mapping xác định và test ownership/identity thay vì dựa vào hành vi “tình cờ” của serializer.

## 24. Null references khi copy

Một shallow copy thường giữ `null` values:

~~~java
class Example {
    Object item;

    Example(Example source) {
        item = source.item; // Nếu null, copy cũng null.
    }
}
~~~

Không có object component để clone khi reference null. Nếu code deep-copy kiểu `new Item(source.item)` phải xử lý null hoặc khai báo precondition non-null.

Một copy constructor cho immutable class có thể đơn giản sao chép immutable reference và null theo contract. Không nên tạo object mới chỉ để “tránh null” nếu điều đó đổi semantics.

## 25. Kế thừa và khả năng sao chép

Khi base class định nghĩa `clone`/copy constructor, subclass có thể bổ sung state riêng; việc copy chỉ biết base fields có thể bỏ sót fields của subclass hoặc làm kết quả type không như mong đợi.

Các tình huống:

- Copy constructor `Base(Base source)` thường tạo **Base object**, không tự tạo runtime subtype nếu truyền Child.
- `super.clone()` có thể giữ runtime class của object được clone nhưng subclass cần bảo vệ state/invariants riêng và mutable nested fields.
- Final/non-final fields, constructor validation và tài nguyên cần semantics đặc biệt.
- Nếu muốn polymorphic copying, cần **API contract rõ ràng** về result type và component sharing, không suy đoán từ tên `clone`.

Với class có invariants phức tạp, nhiều hướng dẫn Java khuyên ưu tiên **factory/copy constructor** hơn giao diện `Cloneable` vì dễ kiểm soát hành vi và test.

### 25.1. Đừng áp dụng `Cloneable` để thể hiện domain equality

“Có thể clone” chỉ là khả năng tạo một object tương tự; nó không nói rằng `equals` phải true, hoặc hai objects phải chia sẻ children, hoặc bản sao có cùng business identity. Tất cả là thiết kế riêng.

## 26. Một copy operation nên cam kết những gì?

Một API tốt cần tài liệu rõ:

- **Outer identity:** kết quả có phải một object mới không, hay có thể trả `this` khi immutable?
- **Component ownership:** object nào được copy, object nào được share?
- **Mutability:** caller có được sửa kết quả không? Việc sửa có ảnh hưởng nguồn không?
- **Depth:** copy một tầng, một subtree, hay một domain snapshot có giới hạn?
- **Aliasing:** shared element objects có được giữ cùng identity không?
- **Null/invariants:** hành vi với optional fields, input invalid?
- **Resources:** owned vs borrowed handles được xử lý thế nào?
- **Concurrency:** input có cần không bị mutate trong lúc copy không?
- **Performance:** copy complexity và mục đích dùng (snapshot, cache, undo, mutation isolation)?
- **Equality:** có cam kết result `equals(source)` không và trường hợp mutable/time-varying fields?

Tên `shallowCopy()` hoặc `snapshot()` có thể giúp giao tiếp contract, nhưng documentation và tests vẫn cần.

## 27. Kiểm thử shallow-copy semantics

Một bộ test hữu ích:

1. **Ngoài khác object:** `original != copy` nếu API cam kết new outer.
2. **Child identity đúng:** `original.child == copy.child` nếu API cam kết shallow share.
3. **Primitive fields copied:** đổi field primitive trong copy không đổi original.
4. **Reference reassignment độc lập:** thay `copy.child = another` không đổi `original.child` nếu outer khác và field mutable.
5. **Shared child mutation:** mutate shared child, hai outer objects đọc value mới.
6. **Structure copied:** `new ArrayList<>(source)` làm add/remove không ảnh hưởng source.
7. **Element references shared:** identity của các mutable elements ban đầu trùng nhau.
8. **Null:** null fields vẫn null theo contract.
9. **Immutable child sharing:** chia sẻ reference tới immutable value không gây mutation.
10. **Deep-copy requirement:** nếu cần độc lập, test cả input alias và getter alias, kể cả nested levels.
11. **Graph invariant:** backlinks/cycles có đúng theo yêu cầu không?
12. **Resources:** close một wrapper có làm wrapper khác bị ảnh hưởng và đó có phải hành vi cho phép?
13. **Concurrency:** nếu sử dụng chung mutable components, có coordination đúng không?
14. **Collections equality/hashing:** tránh thay mutable keys có hash phụ thuộc state.
15. **Performance:** số objects/copy cost phù hợp workload khi bài toán lớn.

**Không cần** phụ thuộc garbage collector để test shallow copying. Hãy kiểm tra object identity `==` và API-visible state một cách deterministic.

### 27.1. Chương trình kiểm thử với assertions luôn được thực hiện

Lưu **`ShallowCopyContractTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowCopyContractTest {
    static final class Item {
        String value;

        Item(String value) {
            this.value = value;
        }
    }

    static void check(boolean ok, String description) {
        if (!ok) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        List<Item> source = new ArrayList<>();
        Item shared = new Item("A");
        source.add(shared);

        List<Item> copy = new ArrayList<>(source);

        check(source != copy, "outer list must differ");
        check(source.get(0) == copy.get(0), "shared element");
        check(source.size() == 1, "source size");

        copy.add(new Item("B"));
        check(source.size() == 1, "structure independent");
        check(copy.size() == 2, "copy size");

        shared.value = "X";
        check("X".equals(source.get(0).value), "source sees child");
        check("X".equals(copy.get(0).value), "copy sees child");

        copy.set(0, new Item("Y"));
        check("X".equals(source.get(0).value),
                "reassignment does not change source item");

        System.out.println("all shallow-copy checks passed");
    }
}
~~~

Chạy:

~~~bash
javac ShallowCopyContractTest.java
java ShallowCopyContractTest
~~~

Output:

~~~text
all shallow-copy checks passed
~~~

Dùng method `check` thay vì Java `assert` vì Java assertions bị tắt mặc định nếu không bật `-ea`. Trong ví dụ này, sai hợp đồng sẽ tạo AssertionError ngay cả khi chạy `java ShallowCopyContractTest` bình thường.

## 28. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`b = a` là sao chép nông.” | Đó chỉ là reference assignment; không tạo outer object mới. |
| “`new Class(source)` đương nhiên là deep copy.” | Copy constructor làm gì phụ thuộc body. |
| “`super.clone()` tự clone tất cả child objects.” | Field-by-field shallow copy mặc định; reference fields vẫn shared. |
| “`Cloneable` có public method clone.” | Cloneable là marker interface, không khai báo clone(). |
| “Clone gọi lại constructor như new.” | Object.clone theo ngữ nghĩa không dùng constructor bình thường như new. |
| “Field `final` làm object con không mutate được.” | Final khóa reference field, không deep freeze referent. |
| “Clone int[] và Item[] đều tách element objects như nhau.” | int values tách; Item references vẫn shared. |
| “Clone int[][] làm mọi hàng riêng.” | Clone outer array vẫn chia sẻ subarrays. |
| “`new ArrayList<>(source)` clone từng phần tử.” | Chỉ copy references; mutable elements shared. |
| “`List.copyOf` deep-copy phần tử.” | Unmodifiable snapshot cấu trúc, không clone element objects. |
| “Unmodifiable view là snapshot.” | Backing collection có thể vẫn thay đổi. |
| “`Map.copyOf` làm mutable values bất biến.” | Values references vẫn có thể shared và mutate. |
| “Shallow copy luôn sai.” | Có thể phù hợp và hiệu quả nếu children immutable hoặc sharing là chủ đích. |
| “Hai lists khác identity thì tất cả elements cũng khác.” | Không; outer vs element identity là hai tầng. |
| “Thay reference trong copy cũng thay original.” | Không nếu outer khác; **mutate shared element** mới ảnh hưởng cả hai. |
| “Một record luôn deep immutable.” | Record có final component references nhưng arrays/mutable elements vẫn chia sẻ. |
| “Copy một parent tự sửa child.parent backlink.” | Không, phải có graph-copy logic riêng. |
| “Thread-safe outer list làm shared mutable child tự thread-safe.” | Không, cần coordination cho child. |
| “Clone resource wrapper tạo resource độc lập.” | Không; resource reference có thể shared và close ảnh hưởng nhau. |
| “Serialization luôn là deep clone an toàn.” | Nhiều giới hạn types/graph/resources/security/performance. |
| “Shallow copy bảo đảm equals true.” | Equality tùy class; outer identity thường khác. |
| “Muốn deep copy thì copy cả String.” | String immutable; copy thường không cần cho mutation safety. |
| “Clone object giải phóng bộ nhớ cũ.” | GC/lifetime không do shallow copy quyết định. |

## 29. Bài tập tự kiểm tra có đáp án

**Câu 1.** `Node b = a;` tạo bao nhiêu Node objects mới?  
**Đáp án:** Không tạo object mới; b giữ cùng reference như a.

**Câu 2.** Shallow copy của Employee có Address reference tạo mấy outer Employees?  
**Đáp án:** Hai outer Employee objects (nếu copy implementation tạo mới), nhưng Address có thể chỉ một object dùng chung.

**Câu 3.** `copy.address == original.address` true biểu thị điều gì?  
**Đáp án:** Cả hai fields giữ cùng reference tới một Address object.

**Câu 4.** `copy.name = "B"` có nhất thiết đổi `original.name` không?  
**Đáp án:** Không nếu copy outer khác và chỉ gán field reference của copy.

**Câu 5.** `copy.address.setCity("Hue")` có thể đổi kết quả đọc original không?  
**Đáp án:** Có nếu Address object shared và method mutate state đó.

**Câu 6.** Vì sao primitive `int count` trong copy độc lập?  
**Đáp án:** Shallow copy copy primitive value, không có primitive object reference chung.

**Câu 7.** `new ArrayList<>(old)` có tạo mới từng Item không?  
**Đáp án:** Không; tạo list mới và sao chép element references.

**Câu 8.** Nếu `copy.set(0,new Item("Y"))`, original list element thay theo không?  
**Đáp án:** Không do list structures khác; original giữ Item cũ.

**Câu 9.** Nếu `copy.get(0).rename(...)` trước khi set, original có thể thấy thay không?  
**Đáp án:** Có nếu cùng Item reference.

**Câu 10.** `List.copyOf` có đồng nghĩa deep clone không?  
**Đáp án:** Không, chỉ snapshot/unmodifiable cấu trúc, element references có thể dùng chung.

**Câu 11.** `Collections.unmodifiableList(source)` có snapshot nội dung khi source mutate không?  
**Đáp án:** Không nhất thiết; thường là live view.

**Câu 12.** `int[] copy = original.clone()` rồi sửa copy[0] có đổi original[0] không?  
**Đáp án:** Không, clone tạo primitive array mới với values copy.

**Câu 13.** `Item[]` clone có tạo Item objects mới không?  
**Đáp án:** Không; references của các phần tử được sao chép.

**Câu 14.** Vì sao `int[][] shallow = matrix.clone()` chưa tách từng row?  
**Đáp án:** Matrix outer array mới nhưng references tới subarrays vẫn shared.

**Câu 15.** `Cloneable` có khai báo method `clone()` public không?  
**Đáp án:** Không. Nó là marker interface.

**Câu 16.** `super.clone()` copy field `Address address` thế nào?  
**Đáp án:** Copy giá trị Address reference, không deep-clone Address.

**Câu 17.** Vì sao copy constructor thường linh hoạt hơn clone?  
**Đáp án:** Có thể validate, chọn fields/components sao chép, kiểm soát constructor/invariant và semantics rõ.

**Câu 18.** Record mới từ record cũ với cùng `int[]` component có tạo array mới không?  
**Đáp án:** Không nếu truyền nguyên component reference.

**Câu 19.** Hai record instances riêng với cùng array reference có thể equal theo generated record equals không?  
**Đáp án:** Có nếu các component values khác cũng equal; array component dùng identity semantics.

**Câu 20.** Vì sao không cần clone String element khi copy List<String>?  
**Đáp án:** String immutable nên chia sẻ reference an toàn về mutation của chính String.

**Câu 21.** Nếu List<MutableItem> được copy, rồi một Item bị mutate, có rủi ro gì?  
**Đáp án:** Cả source và copy có thể quan sát mutation qua shared Item reference.

**Câu 22.** Sao chép danh sách Product references có thích hợp để giữ giá hóa đơn lịch sử không?  
**Đáp án:** Không nếu Product.price mutable và báo giá phải cố định; nên snapshot giá thành immutable OrderLine.

**Câu 23.** Vì sao child.parent backlink không tự trỏ về shallow-copied Parent?  
**Đáp án:** Vì child chính là object cũ, field parent của child chưa được mutate hay copy.

**Câu 24.** Khi graph có cycles, gọi clone recursively vô điều kiện dễ gặp gì?  
**Đáp án:** Recursion vô hạn/StackOverflowError hoặc phá identity-sharing invariants; cần identity map nếu deep-copy graph.

**Câu 25.** Nếu hai copies giữ cùng AtomicInteger, `incrementAndGet` ảnh hưởng kết quả đọc cả hai không?  
**Đáp án:** Có. AtomicInteger là một shared mutable object, dù operations của nó có atomic semantics.

**Câu 26.** Immutable record `Snapshot(int count)` có thay khi AtomicInteger gốc tăng không?  
**Đáp án:** Không; snapshot giữ primitive value được lấy tại thời điểm xây.

**Câu 27.** Copy wrapper chứa socket có tạo socket kết nối mới không?  
**Đáp án:** Không. Nếu reference shared, cả hai wrappers cùng dùng tài nguyên cũ.

**Câu 28.** Thay `copy.child` reference khi outer khác có sửa field original.child không?  
**Đáp án:** Không, trừ khi business code có side effect khác; mỗi outer có field riêng.

**Câu 29.** Muốn immutable Report từ MutableLine, giải pháp là gì?  
**Đáp án:** Copy các giá trị cần lưu sang immutable LineSnapshot elements và tách cấu trúc list.

**Câu 30.** Kiểm thử shallow copy tốt nhất dựa vào điều gì?  
**Đáp án:** Outer/component identity bằng `==`, thay đổi cấu trúc/mutation có kiểm soát và API-visible state, không phụ thuộc GC.

## 30. Checklist triển khai API copy

- [ ] Ghi rõ copy chỉ alias, shallow copy, hay value snapshot/deep copy đến một mức xác định.
- [ ] Xác nhận outer object có tạo mới không và result type là gì.
- [ ] Liệt kê primitive fields và reference fields; reference nào được share?
- [ ] Với array: là primitive array, reference array hay nested array?
- [ ] Với collection: copy structure hay immutable snapshot? elements có mutable?
- [ ] Với map: mutable keys/values và hash contract có ổn định không?
- [ ] Constructor và getter có lộ mutable representation không?
- [ ] Một object bên trong có backlink về owner không? Copy cần sửa links chứ?
- [ ] Có graph cycles hoặc nhiều shared nodes cần giữ identity?
- [ ] Child là immutable value có thể giữ nguyên reference không?
- [ ] Có resource handles không nên clone/copy ownership không?
- [ ] Có thread safety/safe publication yêu cầu khi components shared không?
- [ ] Có tests original vs copy về identity và mutation sau copy không?
- [ ] Đã cân nhắc số allocations và chi phí copy theo workload chưa?

## 31. Tài liệu tham khảo

- Java Platform API Java SE 17, [`Object.clone()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()): field-by-field copying, object identity và contract clone.
- Java Platform API, [`Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): marker interface liên quan clone.
- Java Language Specification Java SE 17, [`10.7 — Array Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.7): array clone semantics.
- Java Language Specification, [`15.10 — Array Creation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10): arrays và thành phần.
- Java Language Specification, [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): giá trị reference.
- Java Platform API, [`Arrays.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): copy arrays.
- Java Platform API, [`ArrayList(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)): cấu trúc list mới với elements của collection.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot semantics.
- Java Platform API, [`Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable map snapshot.
- Java Platform API, [`Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view của backing list.
- Java Platform API, [`HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): equality/hash và keys.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record component values và generated equality.
- Java Platform API, [`AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic shared mutable counter.

## Kết luận

**Sao chép nông** tạo một outer object/container mới nhưng **sao chép các giá trị reference**, không tự tạo bản sao cho mọi object thành phần. Vì thế `original != copy` có thể đúng trong khi `original.child == copy.child` cũng đúng. Mutate shared child thì cả hai có thể thấy thay đổi; gán lại child reference của một outer object khác lại không nhất thiết ảnh hưởng outer còn lại.

Các APIs `super.clone()`, `array.clone()`, `Arrays.copyOf`, `new ArrayList<>(source)` và copy constructor đơn giản đều có thể tạo dạng shallow copy. `List.copyOf`/`Map.copyOf` giữ cấu trúc snapshot unmodifiable nhưng không deep-copy mutable element values; `Collections.unmodifiableList` có thể chỉ là view của backing list.

Chọn **chia sẻ reference khi child immutable hoặc live sharing là chủ đích**. Nếu caller yêu cầu snapshot độc lập, hãy copy các mutable components ở ranh giới thích hợp, bảo vệ constructor/getter aliases và cân nhắc backlinks/cycles, resources cùng concurrency. Đánh giá copy bằng **identity + mutation tests**, đừng chỉ nhìn tên method `clone`/`copy`. Hợp đồng rõ ràng về **“cái gì được tạo mới, cái gì còn được dùng chung”** mới là chìa khóa thiết kế sao chép đối tượng đúng.
