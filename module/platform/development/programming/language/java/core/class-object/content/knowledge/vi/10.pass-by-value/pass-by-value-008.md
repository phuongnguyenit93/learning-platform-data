# Theo dõi tham chiếu qua nhiều lời gọi và nhiều đối tượng trong Java

Một đoạn code Java có nhiều phương thức gọi lồng nhau thường gây nhầm lẫn không phải vì cú pháp khó, mà vì **cùng một đối tượng có thể được tham chiếu bởi nhiều biến thuộc nhiều lần gọi**, trong khi mỗi biến tham chiếu lại có thể được gán sang đối tượng khác.

Hãy bắt đầu bằng một quy tắc tuyệt đối quan trọng:

> **Java luôn truyền đối số bằng giá trị (pass-by-value).** Với đối số có kiểu tham chiếu, giá trị được sao chép sang tham số chính là *giá trị tham chiếu*. Hai biến có thể cùng tham chiếu một object; sửa object có thể quan sát được qua cả hai, nhưng gán lại tham số không làm biến của caller tự đổi tham chiếu.

Ví dụ:

~~~java
Box a = new Box(1);
Box b = a;
change(b);
~~~

Muốn dự đoán biến `a` sẽ quan sát gì sau `change`, ta không thể chỉ nhìn tên biến. Cần biết bên trong `change` có **sửa trạng thái Box hiện có** hay **gán tham chiếu khác cho tham số**. Nếu có các lời gọi `main → first → second → third`, ở mỗi tầng sẽ xuất hiện **biến tham số riêng**, có thể chứa các bản sao tham chiếu đến cùng object.

Bài viết này hướng dẫn phương pháp theo dõi chính xác các tham chiếu trong **chuỗi lời gọi, nhiều object, alias, mảng, object graph, giá trị trả về, vòng lặp/đệ quy, đa hình và xử lý ngoại lệ**. Các ví dụ đầy đủ chạy trên **Java 17+**.

## 1. Bốn thứ luôn phải tách biệt

| Khái niệm | Ví dụ | Có ý nghĩa gì? |
| --- | --- | --- |
| **Object** | Instance `new Account(10)` | Thực thể có identity và trạng thái như field `balance` |
| **Biến tham chiếu** | `Account account` | Biến được khai báo kiểu `Account`, giữ một reference value hoặc `null` |
| **Giá trị tham chiếu** | Giá trị đang lưu trong `account` | Cho phép truy cập một object; có thể được sao chép vào biến khác |
| **Trạng thái object** | `account.balance = 20` | Dữ liệu thuộc object, không phải dữ liệu riêng của mỗi alias |

So sánh hai lệnh:

~~~java
account = new Account(20);
account.balance = 20;
~~~

Giả định `Account` có constructor và field được phép truy cập. **Dòng đầu** tạo một Account mới và gán lại **biến `account`**. **Dòng sau** sửa field của **object hiện được `account` tham chiếu**. Hai hành vi khác nhau dù đều chứa phép gán `=`.

### Sơ đồ tham chiếu là sơ đồ logic

~~~text
main.account --------+
                     |
first.parameter -----+----> Account #1 { balance = 10 }
                     |
second.target -------+
~~~

Các mũi tên trên mô tả **quan hệ tham chiếu**, không phải địa chỉ RAM thật. Java không yêu cầu cách biểu diễn một reference trong JVM phải chính là một con trỏ địa chỉ vật lý mà người lập trình có thể đọc hoặc cộng trừ. Dùng số `#1`, `#2` chỉ là cách **đặt nhãn object theo lần tạo trong bài tập**.

## 2. Bắt đầu theo dõi từ các lần tạo object

Đếm và gán nhãn mỗi object được tạo khi `new` hoàn tất bình thường:

~~~java
Box first = new Box(10);   // Box #1
Box second = new Box(20);  // Box #2
Box alias = first;         // Không có Box #3
~~~

Trạng thái:

~~~text
Biến first  -> Box #1 { value = 10 }
Biến second -> Box #2 { value = 20 }
Biến alias  -> Box #1 { value = 10 }
~~~

Một phép `alias = first` **không clone** Box #1. Đây là **hai biến trỏ một object**. Ngược lại, hai lần `new Box(10)` khác nhau tạo **hai object khác nhau**, dù các field tương ứng có giá trị bằng nhau.

Để dự đoán kết quả của chương trình, hãy dùng hai bảng riêng:

**Bảng reference**

| Biến | Object được tham chiếu |
| --- | --- |
| `first` | #1 |
| `second` | #2 |
| `alias` | #1 |

**Bảng object**

| Object | Trạng thái |
| --- | --- |
| #1 | `value = 10` |
| #2 | `value = 20` |

Khi gặp **phép gán biến reference**, cập nhật bảng reference. Khi gặp **sửa field/element qua reference**, cập nhật bảng trạng thái object. Không tự cập nhật đồng thời cả hai bảng nếu câu lệnh không yêu cầu.

## 3. Một chương trình cơ bản: alias và gán lại biến

Tạo tệp **`AliasTraceDemo.java`**:

~~~java
public class AliasTraceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box left = new Box(1);
        Box right = left;

        right.value = 5;
        right = new Box(9);

        System.out.println("left=" + left.value);
        System.out.println("right=" + right.value);
        System.out.println("same=" + (left == right));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AliasTraceDemo.java
java AliasTraceDemo
~~~

Stdout:

~~~text
left=5
right=9
same=false
~~~

Theo dõi từng câu lệnh:

| Bước | `left` trỏ | `right` trỏ | Box #1 | Box #2 |
| --- | --- | --- | --- | --- |
| `left = new Box(1)` | #1 | Chưa có | `value=1` | Chưa tạo |
| `right = left` | #1 | #1 | `value=1` | Chưa tạo |
| `right.value = 5` | #1 | #1 | `value=5` | Chưa tạo |
| `right = new Box(9)` | #1 | #2 | `value=5` | `value=9` |

Tại bước ba, `right.value = 5` sửa Box #1 nên đọc qua `left` cũng thấy 5. Tại bước bốn, `right` được **gán lại** sang Box #2; `left` vẫn trỏ Box #1.

**Kinh nghiệm:** Trước khi trả lời “biến nào thay đổi?”, cần hỏi **biến reference đổi mũi tên hay trạng thái object đổi field?**

## 4. Mỗi lời gọi phương thức có tham số riêng

Giả sử:

~~~java
static void change(Box parameter) {
    parameter.value = 7;
    parameter = new Box(99);
}

// Trong main:
Box original = new Box(1);
change(original);
~~~

Khi gọi `change(original)`, Java:

1. Đánh giá đối số `original`, thu được giá trị reference đến Box #1.
2. Sao chép giá trị reference ấy vào **tham số `parameter` thuộc lần gọi `change`**.
3. Thực thi các câu lệnh trong `change`.
4. Quay về caller khi lời gọi kết thúc bình thường hoặc chuyển điều khiển theo cơ chế exception.

Sơ đồ ngay khi vào method:

~~~text
main.original ---------+
                       +----> Box #1 { value = 1 }
change.parameter ------+
~~~

Sau `parameter.value = 7`:

~~~text
main.original ---------+
                       +----> Box #1 { value = 7 }
change.parameter ------+
~~~

Sau `parameter = new Box(99)`:

~~~text
main.original --------------> Box #1 { value = 7 }
change.parameter -----------> Box #2 { value = 99 }
~~~

Đây là lý do Java **không có cơ chế “gán lại tham số để sửa biến caller”**. Tham số ở callee là biến riêng, dù tên giống hay khác tên ở caller.

### Chương trình chạy đầy đủ

Lưu **`ParameterRebindingDemo.java`**:

~~~java
public class ParameterRebindingDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void change(Box parameter) {
        parameter.value = 7;
        parameter = new Box(99);
        System.out.println("inside=" + parameter.value);
    }

    public static void main(String[] args) {
        Box original = new Box(1);
        change(original);
        System.out.println("outside=" + original.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterRebindingDemo.java
java ParameterRebindingDemo
~~~

Stdout:

~~~text
inside=99
outside=7
~~~

Không có cơ chế hoàn tác `parameter.value = 7` khi callee kết thúc: thay đổi đã ghi vào object mà caller vẫn tham chiếu.

## 5. Theo dõi chuỗi ba lời gọi: `main → levelOne → levelTwo`

Đây là tình huống trung tâm của bài: **mỗi tầng có một biến tham số**, nhưng các tầng có thể vẫn cùng trỏ một object.

Tạo **`ThreeLevelTraceDemo.java`**:

~~~java
public class ThreeLevelTraceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void levelTwo(Box item) {
        item.value += 10;
        item = new Box(100);
        item.value += 1;
        System.out.println("levelTwo=" + item.value);
    }

    static void levelOne(Box item) {
        item.value += 2;
        levelTwo(item);
        System.out.println("levelOne=" + item.value);
    }

    public static void main(String[] args) {
        Box root = new Box(1);
        levelOne(root);
        System.out.println("main=" + root.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThreeLevelTraceDemo.java
java ThreeLevelTraceDemo
~~~

Stdout:

~~~text
levelTwo=101
levelOne=13
main=13
~~~

### Diễn biến theo thời gian

1. `main` tạo Box #1 có `value = 1`; `root → #1`.
2. `levelOne(root)` tạo một **biến tham số riêng** `item` ở levelOne, có giá trị reference đến #1.
3. `levelOne` thực hiện `item.value += 2`, nên **Box #1 chuyển từ 1 thành 3**.
4. `levelTwo(item)` tạo một **tham số khác**, cũng có tên `item` nhưng thuộc levelTwo, ban đầu tham chiếu #1.
5. `levelTwo` thực hiện `item.value += 10` → **Box #1 thành 13**.
6. `levelTwo` thực hiện `item = new Box(100)` → tạo **Box #2** và chỉ gán lại tham số của levelTwo.
7. `item.value += 1` trong levelTwo sửa **Box #2** thành 101, rồi in `levelTwo=101`.
8. Khi levelTwo kết thúc, code của levelOne tiếp tục với **tham số levelOne vẫn trỏ #1**. In `levelOne=13`.
9. `main` tiếp tục; `root` vẫn trỏ #1 nên in `main=13`.

Sơ đồ ở thời điểm ngay trước khi levelTwo in:

~~~text
main.root -----------------+
                           |
levelOne.item -------------+----> Box #1 { value = 13 }

levelTwo.item -------------------> Box #2 { value = 101 }
~~~

**Đừng để trùng tên `item` đánh lừa:** hai tham số cùng tên ở hai lần gọi không phải một biến. Scope và lần gọi xác định biến nào đang được gán lại.

### Bảng trạng thái chi tiết

| Mốc | `main.root` | `levelOne.item` | `levelTwo.item` | #1 value | #2 value |
| --- | --- | --- | --- | --- | --- |
| Sau `new Box(1)` | #1 | — | — | 1 | — |
| Vào levelOne | #1 | #1 | — | 1 | — |
| Sau `+= 2` | #1 | #1 | — | 3 | — |
| Vào levelTwo | #1 | #1 | #1 | 3 | — |
| Sau `+= 10` | #1 | #1 | #1 | 13 | — |
| Sau `new Box(100)` | #1 | #1 | #2 | 13 | 100 |
| Sau `+= 1` | #1 | #1 | #2 | 13 | 101 |
| Trở về levelOne | #1 | #1 | Kết thúc scope lời gọi | 13 | 101 |
| Trở về main | #1 | Kết thúc scope lời gọi | — | 13 | 101 |

Dấu “—” trong bảng nghĩa là biến của lần gọi đó **chưa tồn tại hoặc không còn hoạt động trong đường thực thi được mô tả**. Nó không hàm ý Box #2 phải bị garbage collector thu hồi ngay.

## 6. Mô hình stack frame: hữu ích nhưng không phải sơ đồ RAM tuyệt đối

Để giải bài tập, có thể biểu diễn các method đang hoạt động như những **khung lời gọi logic**:

~~~text
                 LEVEL TWO đang chạy
+---------------------------------------------+
| levelTwo frame: item -> Box #2              |
+---------------------------------------------+
| levelOne frame: item -> Box #1              |
+---------------------------------------------+
| main frame: root -> Box #1                  |
+---------------------------------------------+

Box #1 { value=13 }       Box #2 { value=101 }
~~~

Mỗi lần gọi có parameter/local variables của **lần gọi đó**. Khi callee kết thúc, caller tiếp tục với các biến của mình. Nhưng đừng suy luận rằng:

- Mỗi reference chắc chắn có một ô stack RAM ở vị trí cố định.
- Object bắt buộc nằm ở một địa chỉ heap không thay đổi.
- JVM không thể inline một method hoặc tối ưu hóa một object.

JIT, garbage collector và JVM implementation có thể dùng các tối ưu hóa khác nhau. Bảng frame và object là **mô hình ngữ nghĩa** để dự đoán hành vi chương trình; kết quả quan sát được vẫn tuân theo quy tắc Java.

## 7. Nhiều object cùng đi qua một chuỗi lời gọi

Khi method nhận hai tham số cùng kiểu, không được giả định chúng luôn trỏ hai object khác nhau.

~~~java
static void transfer(Box source, Box destination) {
    source.value -= 3;
    destination.value += 3;
}
~~~

Có hai trường hợp:

**Trường hợp A: hai object khác nhau**

~~~java
Box a = new Box(10);
Box b = new Box(5);
transfer(a, b);
~~~

Kết quả: object của `a` có 7, object của `b` có 8.

**Trường hợp B: cùng một object**

~~~java
Box a = new Box(10);
transfer(a, a);
~~~

`source` và `destination` là **hai tham số khác nhau**, nhưng cùng trỏ object của `a`. Method trừ 3 rồi cộng 3 trên **chính object đó**, nên giá trị cuối vẫn 10.

Đây là một **mảnh code minh họa** dùng kiểu `Box` có field có thể truy cập; chưa phải file chạy độc lập. Trong một số API nghiệp vụ, việc hai tham số alias nhau phải được **ngăn lại bằng validation**; trong API khác có thể được cho phép. Kiểm tra bằng `source == destination` khi cần so sánh identity.

### Vì sao theo dõi “theo tên biến” chưa đủ?

Trong lời gọi `transfer(a, a)`, hai tham số có hai tên khác nhau nhưng reference values bằng nhau về identity. Nếu chỉ lập bảng “source giảm 3; destination tăng 3” mà quên object dùng chung, bạn sẽ đưa ra kết quả sai. **Phải theo dõi object ID**, không chỉ tên tham số.

## 8. Ví dụ chạy: hai tham số có thể alias

Tạo **`TwoParametersAliasDemo.java`**:

~~~java
public class TwoParametersAliasDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void move(Box from, Box to, int amount) {
        from.value -= amount;
        to.value += amount;
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box second = new Box(5);

        move(first, second, 3);
        System.out.println("distinct=" + first.value + "," + second.value);

        move(first, first, 2);
        System.out.println("same=" + first.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 TwoParametersAliasDemo.java
java TwoParametersAliasDemo
~~~

Stdout:

~~~text
distinct=7,8
same=7
~~~

Với lời gọi đầu, field của hai object độc lập thay đổi. Lời gọi thứ hai dùng **hai bản sao tham chiếu đến cùng Box #1**, nên trừ 2 rồi cộng 2, tổng thay đổi bằng 0. `move` không cần biết tên biến caller; nó làm việc với các **object mà parameters thực sự tham chiếu**.

Trong sản phẩm, phép di chuyển tiền/số lượng cần kiểm tra số âm, tràn số và chính sách chuyển vào chính tài khoản. Ví dụ chỉ nhằm chứng minh alias.

## 9. Theo dõi kết quả trả về qua nhiều tầng

`return` có thể truyền **một giá trị reference** trở lại caller. Nếu method trả về một parameter hoặc field, nó **không tự clone object**.

~~~java
static Box identity(Box value) {
    return value;
}
~~~

Nếu `Box result = identity(original);`, hai biến cùng tham chiếu object ban đầu. Nhưng method cũng có thể trả object mới:

~~~java
static Box copyValue(Box value) {
    return new Box(value.value);
}
~~~

Đó là **mảnh code minh họa**. Khi `new Box(...)` thành công, method trả tham chiếu **đến object mới**; hai object có thể có giá trị field bằng nhau nhưng identity khác nhau.

### Trả về rồi gán lại tại caller

Với:

~~~java
Box current = new Box(1);
current = replace(current);
~~~

nếu `replace` trả reference khác, **phép gán ở caller** khiến `current` đổi mũi tên. Method không thể tự gán lại biến `current` của caller chỉ bằng cách sửa parameter nội bộ.

**Bảng phân biệt:**

| Hành vi bên trong method | Caller quan sát gì? |
| --- | --- |
| Sửa field object chung | Có thể thấy field đã thay đổi |
| Gán lại parameter | Biến caller không tự đổi |
| Trả parameter cũ | Caller có thể nhận cùng reference |
| Trả object mới | Caller có thể nhận reference mới |
| Caller bỏ qua return value | Không tự gán lại biến caller |
| Caller thực hiện `current = method(current)` | Caller chủ động cập nhật reference từ kết quả method |

## 10. Ví dụ chạy: thay object ở tầng giữa bằng `return`

Tạo file **`ReturnReferenceChainDemo.java`**:

~~~java
public class ReturnReferenceChainDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static Box deep(Box parameter) {
        parameter.value += 2;
        return new Box(parameter.value * 10);
    }

    static Box middle(Box parameter) {
        Box result = deep(parameter);
        parameter = result;
        parameter.value += 1;
        return parameter;
    }

    public static void main(String[] args) {
        Box original = new Box(1);
        Box result = middle(original);

        System.out.println("original=" + original.value);
        System.out.println("result=" + result.value);
        System.out.println("same=" + (original == result));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReturnReferenceChainDemo.java
java ReturnReferenceChainDemo
~~~

Stdout:

~~~text
original=3
result=31
same=false
~~~

Theo dõi:

1. `main.original` → Box #1 (1).
2. `middle.parameter` nhận reference #1.
3. `deep.parameter` cũng nhận #1 và thực hiện `+= 2`: Box #1 thành 3.
4. `deep` tạo Box #2 có `value = 3 * 10 = 30`; trả reference #2.
5. `middle.result` → #2, sau đó `middle.parameter = result` chỉ đổi **parameter của middle** thành #2.
6. `parameter.value += 1` trong middle sửa Box #2 thành 31.
7. Middle trả #2; `main.result` nhận reference #2.
8. `main.original` vẫn trỏ #1 và quan sát 3.

Sơ đồ lúc in:

~~~text
main.original ----------> Box #1 { value=3 }
main.result ------------> Box #2 { value=31 }
~~~

Điều dễ sai nhất là dự đoán `original=31` vì nghĩ `parameter = result` đổi luôn biến ở caller. **Không có phép gán như vậy trong main.**

## 11. Giữ nhiều reference ở field: object graph

Không phải mọi reference đều nằm trong local variables. Một object có thể có **field kiểu tham chiếu** đến object khác.

~~~java
class Node {
    String label;
    Node next;
}
~~~

Mỗi Node instance có một field `next`, có thể chứa reference đến Node khác hoặc null. Khi method sửa `node.next`, nó đang **sửa field của Node object** mà `node` tham chiếu. Đây không phải gán lại biến tham số `node`.

Ví dụ:

~~~java
Node first = new Node();
Node second = new Node();
first.next = second;
~~~

Mô hình:

~~~text
first -> Node #1 { next ----------> Node #2 }
second ---------------------------> Node #2
~~~

`first.next` và `second` là **hai chỗ lưu reference có thể trỏ cùng Node #2**. Nếu method gọi `first.next.label = "updated"`, nó sửa label của Node #2, nên đọc `second.label` cũng thấy giá trị mới.

### Field link được gán lại có ảnh hưởng ra sao?

~~~java
Node third = new Node();
first.next = third;
~~~

Sau đó `first.next` trỏ Node #3, nhưng biến `second` vẫn trỏ Node #2. Dòng này **không xóa hay sửa Node #2**; nó thay một reference field bên trong Node #1.

Để làm đúng các bài nhiều object, hãy vẽ cả **mũi tên từ biến tới object** và **mũi tên từ field của object tới object khác**.

## 12. Chương trình object graph: đổi liên kết, không đổi object cũ

Tạo file **`ObjectGraphTraceDemo.java`**:

~~~java
public class ObjectGraphTraceDemo {
    static final class Node {
        String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    static void relink(Node current, Node target) {
        current.next = target;
        target.label = target.label + "!";
        current = target;
        current.next = null;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");

        a.next = b;
        b.next = c;

        relink(a, c);

        System.out.println("a.next=" + a.next.label);
        System.out.println("b.next=" + b.next.label);
        System.out.println("c.label=" + c.label);
        System.out.println("c.next=null: " + (c.next == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ObjectGraphTraceDemo.java
java ObjectGraphTraceDemo
~~~

Stdout:

~~~text
a.next=C!
b.next=C!
c.label=C!
c.next=null: true
~~~

Theo dõi trước lời gọi:

~~~text
a -> Node #1 { label="A", next -> #2 }
b -> Node #2 { label="B", next -> #3 }
c -> Node #3 { label="C", next -> null }
~~~

Trong `relink(a, c)`:

1. `current` ban đầu → #1; `target` → #3.
2. `current.next = target` sửa **field của Node #1**: `#1.next` từ #2 sang #3.
3. `target.label = target.label + "!"` sửa **field của Node #3**: label thành `C!`. Đây là phép gán field mới chứa tham chiếu String; String cũ không bị sửa.
4. `current = target` chỉ gán lại **tham số current** thành #3; biến `a` ở main vẫn → #1.
5. `current.next = null` sửa field `next` của **Node #3**, không phải #1.

Sau lời gọi:

~~~text
a -> Node #1 { label="A", next -> #3 }
b -> Node #2 { label="B", next -> #3 }
c -> Node #3 { label="C!", next -> null }
~~~

Cả `a.next` và `b.next` giờ đều trỏ #3. `b` không được gán lại, nhưng `b.next.label` thay đổi do **Node #3 đang được chia sẻ**. Đây là một mẫu quan trọng của đồ thị đối tượng.

## 13. Khi có hai đường đến cùng object: nested aliasing

Ví dụ:

~~~java
class Person {
    Address address;
}
class Address {
    String city;
}
~~~

Nếu hai Person có field `address` cùng trỏ **một Address instance**, thì thay `personA.address.city` có thể làm `personB.address.city` thay đổi. Hai Person vẫn là **hai object riêng**, nhưng cùng tham chiếu một object con.

Có hai mức alias:

- **Alias trực tiếp:** `a == b` khi hai biến cùng tham chiếu một object.
- **Alias gián tiếp qua field:** `a != b` nhưng `a.address == b.address`.

### Điều cần kiểm tra

Một hàm `updateCity(Person person, String city)` có thể:

~~~java
person.address.city = city;
~~~

hoặc:

~~~java
person.address = new Address(city);
~~~

Dòng đầu sửa **Address object đang được chia sẻ**. Dòng sau sửa **field tham chiếu address của Person object**, chuyển Person đó sang một Address mới; Person khác vẫn có thể dùng Address cũ.

Với bài tập nhiều object, **chỉ vẽ các mũi tên từ biến không đủ**. Phải vẽ liên kết qua field và phần tử mảng.

## 14. Ví dụ chạy: hai Person dùng chung Address

Tạo file **`SharedNestedObjectDemo.java`**:

~~~java
public class SharedNestedObjectDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person {
        final String name;
        Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }
    }

    static void updateSharedAddress(Person person) {
        person.address.city = "Da Nang";
    }

    static void replaceOnlyOneAddress(Person person) {
        person.address = new Address("Hue");
    }

    public static void main(String[] args) {
        Address shared = new Address("Ha Noi");
        Person mai = new Person("Mai", shared);
        Person an = new Person("An", shared);

        updateSharedAddress(mai);

        System.out.println("after update Mai=" + mai.address.city);
        System.out.println("after update An=" + an.address.city);
        System.out.println("same address=" + (mai.address == an.address));

        replaceOnlyOneAddress(mai);

        System.out.println("after replace Mai=" + mai.address.city);
        System.out.println("after replace An=" + an.address.city);
        System.out.println("same address=" + (mai.address == an.address));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SharedNestedObjectDemo.java
java SharedNestedObjectDemo
~~~

Stdout:

~~~text
after update Mai=Da Nang
after update An=Da Nang
same address=true
after replace Mai=Hue
after replace An=Da Nang
same address=false
~~~

Phân tích:

- Ban đầu, `shared`, `mai.address` và `an.address` đều trỏ tới Address #1.
- `updateSharedAddress(mai)` sửa `Address #1.city`. Cả hai Person quan sát `Da Nang`.
- `replaceOnlyOneAddress(mai)` tạo Address #2 và gán `mai.address` sang #2.
- `an.address` vẫn trỏ #1 và giữ thành phố `Da Nang`.
- Không có phép gán nào làm biến `mai` đổi sang một Person khác; **chỉ field của Person Mai được gán lại**.

**Bài học:** “Không thể gán lại biến caller từ parameter” không đồng nghĩa “callee không thể thay đổi tham chiếu được lưu trong object của caller”. Phương thức có thể sửa `person.address` nếu object mutable và quyền truy cập cho phép.

## 15. Mảng cũng tạo đường tham chiếu tới nhiều object

Một biến `Node[]` giữ **reference đến array object**, trong khi từng phần tử của mảng giữ **reference đến Node object hoặc null**.

~~~java
Node first = new Node("A");
Node second = new Node("B");
Node[] nodes = {first, second, first};
~~~

Có ba vị trí phần tử nhưng chỉ **hai Node objects** được tạo. `nodes[0]` và `nodes[2]` cùng trỏ Node A; `nodes[1]` trỏ Node B.

Sơ đồ:

~~~text
nodes -> Array #1
           [0] ----+
           [1] ----|------> Node #2 { label="B" }
           [2] ----+
                    \-----> Node #1 { label="A" }
first ---------------------> Node #1
second --------------------> Node #2
~~~

Nếu một method thực hiện `nodes[0].label = "X"`, cả `nodes[2].label` và `first.label` cũng cho `X`. Nếu nó thực hiện `nodes[0] = new Node("Y")`, **chỉ slot [0]** chuyển sang Node mới; slot [2] và `first` vẫn trỏ Node A.

## 16. Ví dụ chạy: gán phần tử và gán tham số mảng

Tạo file **`ArrayReferenceChainDemo.java`**:

~~~java
public class ArrayReferenceChainDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void edit(Box[] items) {
        items[0].value += 5;
        items[1] = new Box(50);

        items = new Box[] {new Box(100)};
        items[0].value++;
    }

    public static void main(String[] args) {
        Box common = new Box(1);
        Box[] array = {common, common};

        edit(array);

        System.out.println("common=" + common.value);
        System.out.println("slot0=" + array[0].value);
        System.out.println("slot1=" + array[1].value);
        System.out.println("slots same=" + (array[0] == array[1]));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayReferenceChainDemo.java
java ArrayReferenceChainDemo
~~~

Stdout:

~~~text
common=6
slot0=6
slot1=50
slots same=false
~~~

Tại đầu `edit`:

~~~text
main.array ---> Array #1 [0] --> Box #1 { value=1 }
                         [1] --> Box #1 { value=1 }
main.common ------------------> Box #1
edit.items  ---> Array #1
~~~

Trong method:

1. `items[0].value += 5` sửa Box #1 thành 6. Vì hai phần tử lúc này alias nhau, slot 1 cũng *đọc được* 6 trước khi bị thay.
2. `items[1] = new Box(50)` tạo Box #2 và gán **phần tử [1] của Array #1** sang Box #2.
3. `items = new Box[] {new Box(100)}` tạo Array #2 và Box #3, rồi **gán lại parameter items** sang Array #2. `main.array` vẫn trỏ Array #1.
4. `items[0].value++` sửa Box #3 thành 101, không ảnh hưởng Array #1 hoặc Box #1.
5. Trở về `main`: `common` và `array[0]` cùng trỏ Box #1 (6); `array[1]` trỏ Box #2 (50).

**Ba tầng phải theo dõi riêng:** tham số `items`, object mảng và các object nằm trong phần tử mảng. Nhầm một trong ba có thể làm dự đoán stdout sai.

## 17. Primitive trong object không thay đổi cơ chế truyền tham trị

Ví dụ:

~~~java
static void increase(int number) {
    number++;
}

static void increaseBox(Box box) {
    box.value++;
}
~~~

Phương thức đầu nhận **bản sao `int`**. Phương thức sau nhận **bản sao reference đến Box**, nhưng hành vi `box.value++` sửa **primitive field nằm trong Box object đang được chia sẻ**.

Do đó:

~~~java
int number = 5;
increase(number);
// number vẫn 5.

Box box = new Box(5);
increaseBox(box);
// box.value thành 6.
~~~

Các đoạn là mã minh họa, cần class `Box` phù hợp. Không phải “primitive pass-by-value, object pass-by-reference”. **Cả hai đều pass-by-value**. Khác biệt là **giá trị được sao chép là số trực tiếp hay tham chiếu tới object có trạng thái**.

### Trường `final` vẫn có thể tham chiếu object mutable

~~~java
final Box box = new Box(5);
box.value = 9;  // Hợp lệ nếu field có quyền truy cập và mutable.
// box = new Box(1); // Không hợp lệ vì biến box là final.
~~~

`final` trên biến reference ngăn **gán lại biến**, không tự ngăn **sửa Box object**.

## 18. Tham số `final` trong chuỗi lời gọi

Nếu method định nghĩa:

~~~java
static void work(final Box box) {
    box.value += 1;
    // box = new Box(99); // Lỗi biên dịch.
}
~~~

`final` trên tham số ngăn biến `box` được gán lại, nhưng **vẫn cho phép** `box.value += 1` nếu object mutable. Điều này có thể giảm lỗi vô tình đổi reference trong một method, song không làm method “chỉ đọc” object.

Nếu muốn API thật sự không thay đổi input, cần hợp đồng thiết kế:

- Không gọi các mutator trên object được truyền vào.
- Không để lộ mutable aliases hoặc có defensive copy khi phù hợp.
- Dùng immutable/value object khi trạng thái không nên đổi.
- Kiểm thử side effect quan sát được, đặc biệt khi input được chia sẻ ở nhiều tầng.

## 19. So sánh identity và equality trong lúc theo dõi

Với object references, `a == b` trả true nếu chúng cùng biểu thị một object (hoặc cả hai null), trong phạm vi so sánh kiểu hợp lệ. `equals` có thể thể hiện **bằng nhau theo giá trị**, tùy class.

Một record Java 17:

~~~java
record Point(int x, int y) {}
~~~

Nếu:

~~~java
Point first = new Point(1, 2);
Point second = new Point(1, 2);
Point alias = first;
~~~

thì:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `first == second` | false | Hai object được tạo riêng |
| `first.equals(second)` | true | Record equality theo component values |
| `first == alias` | true | `alias` giữ cùng reference |
| `first.equals(alias)` | true | Cùng object và component values |

Khi vẽ **sơ đồ tham chiếu**, dùng **identity** (nhãn #1, #2 hoặc `==`), không gộp hai object chỉ vì `equals` true.

**Tránh dùng `System.identityHashCode` để suy ra địa chỉ hay bảo đảm object ID duy nhất**: giá trị hash identity có thể trùng giữa các object khác nhau và không phải memory address.

## 20. Biến static có thể thêm một đường tham chiếu khác

Reference không chỉ nằm ở local/parameter; nó còn có thể được giữ bởi **static field**. Một method có thể thay static field, tạo tác động quan sát được ngoài các tham số.

Ví dụ:

~~~java
class Registry {
    static Box latest;
}

static void register(Box box) {
    Registry.latest = box;
}
~~~

Nếu `register(original)`, `Registry.latest` và biến `original` cùng trỏ object. Nếu tiếp theo `original = new Box(2)` ở caller, static field **vẫn trỏ object cũ**.

Các đoạn là mã minh họa. Khi giải trace, thêm một hàng vào bảng reference cho **`Registry.latest`**. Static field có thể giữ object còn reachable lâu hơn local variables; việc một frame kết thúc không tự xóa reference ở static field.

Đối với ứng dụng chạy lâu, static caches/registries không giới hạn có thể gây **memory retention**. Không suy luận rằng chỉ cần cho method trả về là mọi object từng tạo trong đó sẽ được thu hồi ngay.

## 21. Gọi instance method và `this`: thêm một đường đến object

Trong instance method, `this` là tham chiếu đến **receiver object** của lời gọi phù hợp.

~~~java
class Counter {
    int value;

    void increase() {
        this.value++;
    }
}
~~~

Nếu:

~~~java
Counter a = new Counter();
Counter b = a;
b.increase();
~~~

thì trong lời gọi `increase`, `this` trỏ **cùng Counter object** với `a` và `b`. Thay đổi `this.value` có thể được quan sát qua cả hai biến.

### `this` không tạo thêm object

Dòng `this.value++` không có `new` và không phải lời gọi constructor. `this(...)` là cú pháp riêng để gọi constructor khác của cùng class **trong constructor**, không được nhầm với `this.field` hay `this.method()`.

Nếu lời gọi method bắt đầu từ field:

~~~java
container.item.increase();
~~~

thì receiver `this` của `increase` là **Counter object mà `container.item` hiện tham chiếu**, không phải object `container`.

## 22. Đa hình: kiểu của biến có thể khác kiểu runtime của object

Theo dõi tham chiếu không được đồng nhất **kiểu khai báo** với **runtime class**.

~~~java
Animal pet = new Dog();
~~~

Nếu `Dog extends Animal`, biến `pet` có **kiểu khai báo Animal** nhưng trỏ **Dog instance**. Phép gán:

~~~java
Animal samePet = pet;
~~~

chỉ sao chép reference; không tạo một Animal object khác.

**Overriding:** Instance method được override có thể dispatch theo runtime class Dog. **Overloading:** Compiler chọn chữ ký overload theo kiểu biểu thức tại compile time. Hai cơ chế không giống nhau và có thể xuất hiện đồng thời.

### Ví dụ chạy độc lập

Tạo **`PolymorphicTraceDemo.java`**:

~~~java
public class PolymorphicTraceDemo {
    static class Animal {
        String sound() {
            return "?";
        }
    }

    static final class Dog extends Animal {
        @Override
        String sound() {
            return "woof";
        }
    }

    static void inspect(Animal parameter) {
        System.out.println("sound=" + parameter.sound());
        parameter = new Dog();
        System.out.println("new sound=" + parameter.sound());
    }

    public static void main(String[] args) {
        Dog dog = new Dog();
        Animal animal = dog;

        inspect(animal);

        System.out.println("same=" + (animal == dog));
        System.out.println("sound after=" + animal.sound());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PolymorphicTraceDemo.java
java PolymorphicTraceDemo
~~~

Stdout:

~~~text
sound=woof
new sound=woof
same=true
sound after=woof
~~~

`inspect(parameter)` ban đầu giữ reference đến Dog #1; lần gọi `parameter.sound()` dùng triển khai Dog. Sau `parameter = new Dog()`, parameter trỏ Dog #2, nhưng `animal` và `dog` ở caller vẫn trỏ Dog #1. Vì cả hai object đều là Dog nên output `woof` không đủ để phân biệt identity; dòng `same=true` xác nhận hai biến **ở caller** vẫn cùng object.

**Kỹ thuật khi hai object in cùng dữ liệu:** Thêm so sánh `==` hoặc gán cho object một ID logic để tránh suy luận rằng các output giống nhau tức là cùng object.

## 23. Đệ quy: cùng tên parameter, nhiều lần gọi khác nhau

Trong đệ quy, method có thể gọi chính nó, nhưng **mỗi lần gọi có bộ tham số/local riêng**.

~~~java
static void walk(Node current, int depth) {
    if (current == null) {
        return;
    }
    System.out.println(depth + ":" + current.label);
    walk(current.next, depth + 1);
}
~~~

Nếu có chuỗi Node #1 → #2 → #3 → null, thì:

~~~text
walk(#1,0) frame 1: current -> #1
  walk(#2,1) frame 2: current -> #2
    walk(#3,2) frame 3: current -> #3
      walk(null,3) frame 4: current -> null, return
    return frame 3
  return frame 2
return frame 1
~~~

Một lời gọi ở độ sâu 2 gán lại `current` không làm `current` ở độ sâu 1 tự đổi. Các tham số có tên giống nhau nhưng khác **lần gọi**, giống trường hợp method chain nhiều tầng.

### Cẩn thận với chu kỳ

Nếu `last.next = first` tạo vòng trong linked nodes, method `walk` trên có thể lặp đệ quy vô hạn cho đến `StackOverflowError`. Đồ thị tham chiếu Java cho phép chu kỳ; đừng giả định cấu trúc luôn là một chuỗi kết thúc null.

## 24. Ví dụ chạy: trace đệ quy và thay tham số tại từng tầng

Tạo file **`RecursiveReferenceTraceDemo.java`**:

~~~java
public class RecursiveReferenceTraceDemo {
    static final class Node {
        final String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    static void walk(Node current, int depth) {
        if (current == null) {
            System.out.println("end depth=" + depth);
            return;
        }

        System.out.println(depth + ":" + current.label);
        Node next = current.next;
        current = null;
        walk(next, depth + 1);
    }

    public static void main(String[] args) {
        Node first = new Node("A");
        Node second = new Node("B");
        first.next = second;

        walk(first, 0);

        System.out.println("first.next=" + first.next.label);
        System.out.println("second=" + second.label);
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecursiveReferenceTraceDemo.java
java RecursiveReferenceTraceDemo
~~~

Stdout:

~~~text
0:A
1:B
end depth=2
first.next=B
second=B
~~~

Trong từng frame:

1. Lưu `current.next` vào local `next`, nên vẫn giữ reference đến node kế tiếp.
2. `current = null` chỉ gán lại tham số của **frame hiện tại**, không xóa node và không gán `first = null` hay `first.next = null`.
3. `walk(next, depth + 1)` truyền **bản sao reference** tới node tiếp theo cho frame mới.
4. Sau khi mọi lời gọi trở về, `first.next` vẫn trỏ Node B; `second` vẫn trỏ Node B.

Dòng `current = null` **không giải phóng object ngay**; các alias khác và field `first.next` vẫn giữ object reachable. Mục đích của dòng này chỉ là minh họa phép gán lại một parameter.

## 25. Object graph có chu kỳ và kiểm tra đã duyệt

Một cấu trúc có thể chia sẻ hoặc có chu kỳ:

~~~text
Node A.next -> Node B
Node B.next -> Node C
Node C.next -> Node A
~~~

Không thể duyệt bằng thuật toán “đi tiếp cho tới khi `null`” nếu mọi cạnh đều tạo vòng. Cần ghi nhận những **object identities đã được thăm**. Với một số API, `HashSet<Node>` dựa trên `equals/hashCode`; nếu Node override equality theo giá trị, hai object khác nhau có thể bị coi như một. Khi mục tiêu là truy vết **identity**, có thể dùng tập backed by `IdentityHashMap`.

Ví dụ minh họa:

~~~java
java.util.Set<Node> visited =
        java.util.Collections.newSetFromMap(
                new java.util.IdentityHashMap<>());

Node current = first;
while (current != null && visited.add(current)) {
    System.out.println(current.label);
    current = current.next;
}
~~~

Đây là **mảnh mã minh họa**, cần `Node` và `first` phù hợp. `visited.add(current)` chỉ trả true khi reference đến một Node object chưa được ghi nhận theo **identity**, nên vòng dừng khi gặp lại cùng object.

Dùng identity tracking khi vấn đề là **đồ thị reference**, không tự thay thế equality theo nghiệp vụ bằng identity trong mọi collection. Nếu mục tiêu là so sánh hai sản phẩm cùng ID, `equals` theo domain có thể phù hợp hơn.

## 26. Lỗi ném ở tầng sâu không tự hoàn tác sửa object ở tầng trên

Một lời gọi có thể sửa object chung rồi ném exception. Nếu caller bắt exception, object có thể **vẫn mang trạng thái đã thay đổi**.

Tạo file **`ExceptionReferenceTraceDemo.java`**:

~~~java
public class ExceptionReferenceTraceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void deepest(Box item) {
        item.value += 10;
        throw new IllegalStateException("stop");
    }

    static void middle(Box item) {
        item.value += 2;
        deepest(item);
        item.value += 100; // Không được chạy.
    }

    public static void main(String[] args) {
        Box original = new Box(1);

        try {
            middle(original);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("after=" + original.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExceptionReferenceTraceDemo.java
java ExceptionReferenceTraceDemo
~~~

Stdout:

~~~text
caught=stop
after=13
~~~

Theo dõi:

- `main.original`, `middle.item`, `deepest.item` đều ban đầu trỏ Box #1.
- `middle` cộng 2, Box #1 từ 1 thành 3.
- `deepest` cộng 10, Box #1 từ 3 thành 13.
- `deepest` ném `IllegalStateException`. Câu lệnh `item.value += 100` sau lời gọi `deepest` trong middle **không chạy**.
- `catch` ở main xử lý exception, nhưng **không rollback** hai phép sửa object đã thực hiện, nên `after=13`.

Nếu quy tắc nghiệp vụ cần thay đổi **nguyên tử**, phải thiết kế giao dịch, state copy hoặc cơ chế phục hồi phù hợp; không thể coi việc ném exception là phép hoàn tác object tự động.

## 27. Thứ tự đánh giá đối số ảnh hưởng việc trace

Java đánh giá các biểu thức đối số **từ trái sang phải**. Nếu chúng có side effect trên cùng object, giá trị được chuyển vào method sau đó có thể khác kỳ vọng.

Tạo **`ArgumentTraceDemo.java`**:

~~~java
public class ArgumentTraceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static int bump(Box box) {
        box.value++;
        System.out.println("bump=" + box.value);
        return box.value;
    }

    static void receive(Box box, int before, int after) {
        System.out.println("receive=" + box.value + "," + before + "," + after);
    }

    public static void main(String[] args) {
        Box box = new Box(1);

        receive(box, bump(box), bump(box));

        System.out.println("main=" + box.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentTraceDemo.java
java ArgumentTraceDemo
~~~

Stdout:

~~~text
bump=2
bump=3
receive=3,2,3
main=3
~~~

Giải thích:

1. Đối số đầu `box` được đánh giá: reference tới Box #1.
2. Đối số thứ hai `bump(box)` được gọi, sửa Box #1 thành 2, trả `int 2`.
3. Đối số thứ ba `bump(box)` chạy, sửa cùng Box #1 thành 3, trả `int 3`.
4. Method `receive` bắt đầu; tham số Box trỏ cùng Box #1 có trạng thái **hiện tại là 3**, còn `before` và `after` giữ **các giá trị primitive 2 và 3** đã tính.
5. `main` tiếp tục thấy `box.value = 3`.

Không có ba Box instances. Đây chỉ là **một object** được đọc/sửa qua nhiều lời gọi. Trong code thực tế, tránh side effect phức tạp ngay trong danh sách đối số nếu khiến thứ tự khó hiểu.

## 28. Phân biệt tạo mới trong callee và tạo mới trước lời gọi

Hai lời gọi nhìn có vẻ tương tự:

~~~java
replace(new Box(5));
~~~

và:

~~~java
Box original = new Box(5);
replace(original);
~~~

Ở cả hai, callee nhận bản sao reference đến một Box object. Khác biệt là caller thứ hai **lưu riêng reference** `original` để còn có thể dùng sau lời gọi; caller thứ nhất không lưu trực tiếp result của `new` vào biến từ chính câu lệnh đó.

Nhưng đừng kết luận object của lời gọi đầu luôn bị thu hồi ngay khi method trả về. Callee có thể trả reference, gán vào field hoặc đưa object vào collection khác, làm object tiếp tục reachable. Việc có bao nhiêu alias và chúng nằm ở đâu mới xác định đường truy cập object, không phải chỉ dựa trên code có biến local tên `original` hay không.

## 29. Lỗi thường gặp khi trace qua nhiều method

| Cách suy luận sai | Vì sao sai? | Cách khắc phục |
| --- | --- | --- |
| “Tham số object là biến của caller.” | Tham số là biến riêng của lần gọi, chỉ nhận bản sao reference. | Vẽ frame riêng cho caller/callee. |
| “Đổi `parameter = new X()` làm caller trỏ object mới.” | Chỉ gán parameter. | Ghi lại mũi tên của đúng biến được gán. |
| “Nếu sửa field trong callee thì caller không biết.” | Hai reference có thể trỏ cùng mutable object. | Cập nhật bảng state của object chung. |
| “Hai tham số khác tên luôn là hai object.” | Caller có thể truyền cùng reference vào cả hai. | Kiểm tra identity của từng parameter. |
| “Cùng tên parameter ở hai method là một biến.” | Hai lần gọi có scope/frame riêng. | Nhãn `middle.item` và `deep.item`. |
| “Hai object có cùng dữ liệu là một object.” | Identity khác equality theo giá trị. | Đếm lần tạo, gán nhãn object ID. |
| “Gán `node.next = x` làm `node` đổi reference.” | Đây là gán một **field reference**, không gán biến `node`. | Theo dõi mũi tên từ field. |
| “Mảng chỉ là danh sách giá trị, không phải object.” | Mảng có identity và các reference elements. | Vẽ array object và từng slot. |
| “`final` làm object không sửa được.” | Nó ngăn gán lại biến/field, không tự làm object immutable. | Tách reference immutability và object mutability. |
| “Method trả reference thì clone object.” | `return parameter;` có thể trả cùng object. | Tìm nơi tạo object mới thực sự. |
| “Cast hoặc upcast tạo object mới.” | Chuyển đổi kiểu reference hợp lệ không clone instance. | Giữ nguyên object ID sau cast. |
| “Đệ quy thay parameter tầng sâu thì tầng trên cũng đổi.” | Mỗi recursive call có parameter riêng. | Lập bảng theo depth/frame. |
| “Ném exception khôi phục mọi field cũ.” | Side effect không được tự rollback. | Theo dõi mọi sửa đổi trước exception. |
| “Đối số được tính đồng thời.” | Java đánh giá theo thứ tự từ trái sang phải. | Trace side effect trong lúc đánh giá. |
| “Object vừa hết local scope sẽ GC ngay.” | Có thể còn alias, field, return, static reference. | Theo dõi reachability, không suy đoán lịch GC. |

## 30. Phương pháp giải bài trace trong sáu bước

Với một bài có nhiều method/class và các phép gán rối, hãy thực hiện **tuần tự**:

**Bước 1 — Liệt kê các object và đặt nhãn.** Mỗi biểu thức tạo instance/mảng được thực thi thành công nhận ID `#1`, `#2`, ...; không tính phép gán reference là tạo mới.

**Bước 2 — Lập bảng object state.** Ghi field primitive, field reference, array elements. Với reference fields, ghi object ID đích thay vì chỉ ghi `"có object"`.

**Bước 3 — Lập bảng biến theo frame.** Không gộp biến `item` của method A với `item` của method B. Ghi `main.item`, `A.item`, `B.item`, hoặc theo số lần gọi nếu đệ quy.

**Bước 4 — Đi theo execution order.** Đánh giá đối số, gọi method, chạy các câu lệnh trong đúng thứ tự, rồi quay lại caller. Với exception, theo đường unwind chứ không chạy tiếp dòng sau lệnh ném.

**Bước 5 — Phân loại từng phép gán.** Nếu vế trái là **biến reference/parameter**, chỉ đổi mục tiêu của biến đó. Nếu là **field hoặc array slot**, sửa liên kết/trạng thái bên trong object đang được tham chiếu. Nếu là **primitive field**, sửa giá trị trong object; nếu là primitive parameter, chỉ sửa parameter.

**Bước 6 — Tính output từ trạng thái đúng thời điểm.** `println` đọc field **lúc nó chạy**, không phải lúc reference được gán. Với `==`, hỏi cùng object identity; với `equals`, xem hợp đồng cụ thể của class.

### Mẫu bảng có thể sao chép ra giấy

| Lệnh / mốc | Frame | Biến thay reference | Object / field thay đổi | Output |
| --- | --- | --- | --- | --- |
| `new Box(1)` | main | `main.a → #1` | Tạo #1, `value=1` | — |
| `call(a)` | callee | `callee.p → #1` | Không tự sửa field | — |
| `p.value++` | callee | Không | `#1.value: 1 → 2` | — |
| `p = new Box(9)` | callee | `callee.p → #2` | Tạo #2, `value=9` | — |
| `return` | callee → main | Biến callee ngừng hoạt động | #1 vẫn `value=2` | — |
| `println(a.value)` | main | Không | Không | `2` |

Mẫu này phù hợp cho cả **một chuỗi gọi thường**, **lời gọi đệ quy** và **object graph** nếu bổ sung cột liên kết giữa các field.

## 31. Bài luyện tập 1 — Hai đường qua cùng một object

Cho hai class:

~~~java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

static void apply(Box first, Box second) {
    first.value += 4;
    second = new Box(50);
    second.value += 2;
}
~~~

Giả sử method `apply` nằm trong class phù hợp. Caller:

~~~java
Box a = new Box(1);
Box b = a;
apply(a, b);
System.out.println(a.value);
System.out.println(b.value);
System.out.println(a == b);
~~~

**Tự dự đoán rồi kiểm tra:** stdout là

~~~text
5
5
true
~~~

Giải thích: hai biến caller đều trỏ Box #1. `first.value += 4` sửa #1 thành 5. `second = new Box(50)` tạo Box #2 và đổi **chỉ tham số second**; nó không gán lại caller `b`. Sau khi method kết thúc, `a` và `b` vẫn cùng #1.

## 32. Bài luyện tập 2 — Đổi field reference trong object chung

Giả sử:

~~~java
class Holder {
    Box value;
}

static void attach(Holder holder, Box box) {
    holder.value = box;
    box = new Box(99);
}
~~~

Caller:

~~~java
Holder h = new Holder();
Box a = new Box(7);
attach(h, a);
System.out.println(h.value == a);
System.out.println(h.value.value);
~~~

Stdout:

~~~text
true
7
~~~

`holder.value = box` sửa **field của Holder object**; nó được phép làm `h.value` ở caller trỏ Box #1. Nhưng `box = new Box(99)` chỉ gán lại parameter `box`. Không có lệnh nào đặt `h.value` sang Box #2.

Các đoạn của hai bài là **mảnh mã để ghép vào file Java hợp lệ**, không phải chương trình độc lập. Cần đặt static method trong class và dùng class Box/Holder tương ứng.

## 33. Bài luyện tập 3 — Hai object liên kết qua field

~~~java
class Node {
    Node next;
    int value;

    Node(int value) {
        this.value = value;
    }
}

static void modify(Node n) {
    Node oldNext = n.next;
    n.next = new Node(30);
    oldNext.value += 5;
}
~~~

Caller:

~~~java
Node a = new Node(1);
Node b = new Node(2);
a.next = b;
modify(a);
System.out.println(a.next.value);
System.out.println(b.value);
System.out.println(a.next == b);
~~~

Stdout:

~~~text
30
7
false
~~~

Trong `modify`, `oldNext` giữ reference đến Node `b` **trước** khi `n.next` được gán sang Node mới. Gán lại field `n.next` không làm `oldNext` mất object cũ. `oldNext.value += 5` vì vậy tăng Node B từ 2 lên 7. Đồ thị sau khi gọi có `a.next → Node mới (30)` và `b → Node cũ (7)`.

## 34. Bài luyện tập 4 — Trả reference đi qua hai tầng

~~~java
static Box inner(Box input) {
    input.value++;
    return input;
}

static Box outer(Box input) {
    Box returned = inner(input);
    returned = new Box(returned.value + 5);
    return returned;
}
~~~

Caller:

~~~java
Box a = new Box(1);
Box b = outer(a);
System.out.println(a.value);
System.out.println(b.value);
System.out.println(a == b);
~~~

Stdout:

~~~text
2
7
false
~~~

`inner` sửa Box #1 thành 2 và trả chính reference #1. `outer` tạo Box #2 với giá trị 7 rồi trả #2. Caller `a` tiếp tục trỏ #1 (2), `b` trỏ #2 (7). Gán biến `returned` trong outer không tự gán `a` ở main.

## 35. Bài luyện tập 5 — Các tham số đệ quy không phải một biến

~~~java
static void visit(Box box, int depth) {
    if (depth == 0) {
        return;
    }

    box.value++;
    Box next = new Box(box.value);
    visit(next, depth - 1);
}
~~~

Caller:

~~~java
Box first = new Box(1);
visit(first, 3);
System.out.println(first.value);
~~~

Output là `2`. Ở depth 3, method sửa Box #1 từ 1 thành 2, tạo Box #2 có 2 rồi gọi depth 2 trên Box #2. Ở depth 2, method sửa Box #2 từ 2 thành 3, tạo Box #3; ở depth 1, nó sửa Box #3 từ 3 thành 4. Những object mới không tự là biến `first`; vì vậy `first.value` vẫn 2.

Đây là mảnh mã minh họa, không phải chương trình chạy độc lập. Bài học là **trace từng frame và từng lần `new`** thay vì tính tất cả phép tăng lên một object duy nhất.

## 36. Tình huống cần lưu ý khi thực hành thực tế

### Null reference

Nếu parameter nhận null, `parameter = new Box(...)` là phép gán lại hợp lệ cho biến parameter nhưng không cập nhật caller. Nếu trước đó code gọi `parameter.value` khi parameter null, NPE sẽ xảy ra. Khi trace, ghi rõ mũi tên “null” thay vì vẽ một object giả.

### Immutable objects

`String` là reference type nhưng immutable. `text = text + "!"` thường khiến biến `text` tham chiếu chuỗi kết quả mới; nó không sửa chuỗi cũ do các alias khác đang giữ. Do đó chia sẻ reference không luôn tạo khả năng sửa trạng thái: **object mutable hay immutable** quyết định phần này.

### Constructor/factory

Nếu một constructor/factory tạo hai object và liên kết chúng qua field, phải vẽ từng object và field link. Một constructor ném exception không trả reference thành công cho caller từ biểu thức `new`, nhưng các side effect đã thực hiện trước exception không tự rollback.

### Collection copy

`new ArrayList<>(existing)` tạo collection object mới nhưng **sao chép reference phần tử**. Hai collection có thể không alias nhau ở cấp container nhưng vẫn dùng chung các element objects mutable. Đây là shallow copy; muốn độc lập sâu phải có chiến lược copy sâu theo mô hình dữ liệu.

### Nhiều thread

Nếu hai thread cùng sửa một mutable object qua các reference alias, cần các quy tắc đồng bộ/atomicity/visibility của Java Memory Model. Bảng trace **tuần tự** ở bài này không tự chứng minh chương trình đa luồng thread-safe. Đặc biệt `value++` không phải phép tăng atomic cho nhiều thread.

### Garbage collection

Khi một parameter hoặc local hết thời gian hoạt động, object không nhất thiết bị thu hồi ngay: field/static/array/return value hoặc alias khác có thể vẫn giữ object reachable. Không sử dụng `System.gc()` hay `identityHashCode` để “chứng minh” object nào vừa biến mất.

## 37. Checklist tự đánh giá

- [ ] Tôi có thể phân biệt biến reference, reference value, object identity và trạng thái field.
- [ ] Tôi biết mỗi lần gọi method có các parameter/local riêng của **lần gọi đó**.
- [ ] Tôi biết Java truyền **bản sao reference value**, không truyền biến caller theo tham chiếu.
- [ ] Tôi có thể vẽ bảng hai cột: **biến → object ID**, **object ID → trạng thái**.
- [ ] Tôi xác định đúng khi `p = new X()` chỉ gán lại parameter.
- [ ] Tôi xác định đúng khi `p.field = ...` sửa object mà caller vẫn có thể tham chiếu.
- [ ] Tôi dự đoán được kết quả khi cùng object được truyền qua **hai tham số**.
- [ ] Tôi theo dõi được reference qua chuỗi `main → A → B → C` và khi trở về.
- [ ] Tôi biết `return parameter;` không tự clone object và caller phải chủ động gán result nếu muốn đổi reference.
- [ ] Tôi biết object có thể chứa **field reference** đến object khác và tạo đồ thị alias nhiều tầng.
- [ ] Tôi phân biệt sửa field link với gán lại biến đang giữ object.
- [ ] Tôi biết array là object; array slots có thể giữ các reference tới cùng element object.
- [ ] Tôi phân biệt primitive field thay đổi với primitive parameter thay đổi.
- [ ] Tôi phân biệt `final` reference với immutable object.
- [ ] Tôi phân biệt identity bằng `==` và equality theo `equals`.
- [ ] Tôi hiểu upcasting không tạo object mới và overriding dispatch theo runtime object.
- [ ] Tôi biết mỗi recursive call có frame/parameter riêng; sửa reference ở tầng sâu không sửa biến tầng trên.
- [ ] Tôi theo dõi các side effect trên object trước khi exception được ném.
- [ ] Tôi tính đúng thứ tự đánh giá đối số từ trái qua phải.
- [ ] Tôi không dự đoán GC hoặc địa chỉ RAM từ mô hình sơ đồ mũi tên.
- [ ] Tôi tự biên dịch, chạy và giải thích từng stdout của các chương trình Java 17+ trong bài.

**Kết luận:** Để theo dõi tham chiếu qua nhiều lời gọi và nhiều đối tượng, đừng hỏi “biến object này được truyền theo tham chiếu hay giá trị?”. Java đã có câu trả lời: **luôn truyền bằng giá trị**. Hãy hỏi chi tiết hơn: **mỗi tham số đang giữ bản sao reference nào; object nào được tạo; field/array slot nào bị sửa; biến nào được gán lại; và reference nào được trả về?** Tách những câu hỏi đó thành bảng theo từng lần gọi và từng object là phương pháp ổn định để dự đoán đúng mọi thay đổi trong những bài trace Java.
