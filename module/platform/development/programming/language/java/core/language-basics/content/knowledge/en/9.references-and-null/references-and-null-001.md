# Biến tham chiếu và đối tượng mà biến tham chiếu tới — Java 17+

Trong Java, khi khai báo `Box item = new Box(10);`, ta cần phân biệt **biến tham chiếu `item`** với **đối tượng `Box` được tạo bởi `new`**.

- **Biến tham chiếu** có một kiểu khai báo (ví dụ `Box`), có thể chứa giá trị tham chiếu tới đối tượng tương thích hoặc `null`. Biến này có thể được gán lại nếu không bị ràng buộc bởi `final`.
- **Đối tượng** mang trạng thái và hành vi riêng theo lớp của nó. Hai biến có thể cùng tham chiếu đến **một đối tượng**; khi đó thao tác thay đổi trạng thái đối tượng qua một biến có thể quan sát qua biến còn lại.
- **Phép gán tham chiếu không nhân bản đối tượng.** Trong `Box other = item;`, giá trị tham chiếu được sao chép, chứ không tự có thêm một `Box`.
- `null` có nghĩa là **không tham chiếu đến đối tượng nào**, không phải một đối tượng đặc biệt có trường hoặc phương thức.

Đây là **ngữ nghĩa** của Java, không cần giả định địa chỉ bộ nhớ, vị trí stack/heap hay cách JVM tối ưu đối tượng.

## 1. Bốn thao tác trông giống nhau nhưng khác bản chất

~~~java
Box first = new Box("Main", 10); // Tao mot doi tuong, first tham chieu toi no.
Box alias = first;        // Copy tham chieu, KHONG tao Box moi.
Box another = new Box("Other", 10); // Tao Box khac, du co cung gia tri.
alias = null;             // Chi thay doi bien alias.
~~~


| Thao tác | Biến thay đổi? | Đối tượng thay đổi? |
| --- | --- | --- |
| `Box first = new Box("Main", 10);` | `first` nhận tham chiếu | Có đối tượng mới được tạo |
| `Box alias = first;` | `alias` nhận bản sao tham chiếu | Không tự tạo hoặc sửa đối tượng |
| `alias.points = 20;` | Tham chiếu trong `alias` không đổi | Đối tượng chung được sửa nếu field cho phép |
| `alias = new Box("Fresh", 5);` | `alias` trỏ sang đối tượng khác | Đối tượng cũ không bị thay bằng đối tượng mới |
| `alias = null;` | `alias` không còn trỏ tới đối tượng | Bản thân đối tượng cũ không tự bị xóa ngay |
| `Box independent = new Box("Independent", 20);` | `independent` giữ tham chiếu riêng | Có đối tượng mới, dù dữ liệu trùng nhau |

Các đoạn ở mục này dùng cùng constructor `Box(String label, int points)` và field `points` trong chương trình ở mục 2; những đoạn ví dụ này chỉ cần đặt vào phạm vi thích hợp sau định nghĩa lớp `Box` để thử lại.

Hãy hình dung:

~~~text
first ───┐
         ├──────> Box(points=10)
alias ───┘

another ────────> Box(points=10)   // Doi tuong khac

alias = null;
first ──────────> Box(points=10)
alias ──────────> null
~~~

Sơ đồ chỉ mô tả **quan hệ tham chiếu**, không mô tả địa chỉ RAM hay cơ chế quản lý bộ nhớ vật lý.

## 2. Ví dụ Java 17+ chạy độc lập

Lưu tệp UTF-8 tên **`ReferenceObjectDemo.java`**:

~~~java
public class ReferenceObjectDemo {
    static class Box {
        final String label;
        int points;

        Box(String label, int points) {
            this.label = label;
            this.points = points;
        }
    }

    static void increase(Box parameter) {
        parameter.points += 5; // Sua doi tuong dang duoc tham chieu.
    }

    static void replace(Box parameter) {
        parameter = new Box("Replacement", 99);
        System.out.println("insideReplace=" + parameter.points);
    }

    public static void main(String[] args) {
        Box first = new Box("Main", 10);
        Box alias = first;
        Box separate = new Box("Main", 10);

        System.out.println("aliasSameObject=" + (first == alias));
        System.out.println("separateSameObject=" + (first == separate));

        alias.points = 20;
        System.out.println("firstAfterAlias=" + first.points);
        System.out.println("separatePoints=" + separate.points);

        increase(first);
        System.out.println("afterIncrease=" + first.points);

        replace(first);
        System.out.println("afterReplace=" + first.points);

        alias = null;
        System.out.println("aliasIsNull=" + (alias == null));
        System.out.println("firstStillWorks=" + first.points);

        Box old = first;
        first = new Box("Fresh", 7);
        System.out.println("newObject=" + first.points);
        System.out.println("oldObject=" + old.points);

        final Box fixedReference = old;
        fixedReference.points = 30;
        System.out.println("finalReferencePoints=" + old.points);

        Box absent = null;
        System.out.println("absentIsNull=" + (absent == null));
        try {
            System.out.println(absent.points);
        } catch (NullPointerException ex) {
            System.out.println("dereference=NullPointerException");
        }

        Box[] slots = new Box[2];
        System.out.println("defaultArrayElementNull=" + (slots[0] == null));
        slots[0] = old;
        System.out.println("arraySharesObject=" + (slots[0] == old));
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) ở thư mục chứa tệp, dùng JDK 17+:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ReferenceObjectDemo.java
java ReferenceObjectDemo
~~~

**Expected output của chương trình** (không tính các dòng phiên bản do `java -version` và `javac -version` in ra):

~~~text
aliasSameObject=true
separateSameObject=false
firstAfterAlias=20
separatePoints=10
afterIncrease=25
insideReplace=99
afterReplace=25
aliasIsNull=true
firstStillWorks=25
newObject=7
oldObject=25
finalReferencePoints=30
absentIsNull=true
dereference=NullPointerException
defaultArrayElementNull=true
arraySharesObject=true
~~~

### Phân tích kết quả

1. `alias = first` làm hai biến trỏ cùng đối tượng, vì thế `first == alias` là `true`. `separate` được tạo bằng lần `new` khác; dữ liệu giống nhau không biến nó thành cùng một đối tượng.
2. `alias.points = 20` làm `first.points` thành 20. Không phải “biến `first` bị sửa tham chiếu”; **trạng thái của đối tượng chung** đã thay đổi.
3. Phương thức `increase` nhận bản sao tham chiếu. Nó vẫn truy cập cùng đối tượng và tăng `points` lên 25.
4. `replace` chỉ gán lại **tham số cục bộ** sang `Box` mới. Biến `first` của bên gọi vẫn trỏ tới đối tượng có `points = 25`.
5. Gán `alias = null` không làm đối tượng biến mất vì `first` vẫn giữ tham chiếu. Khi gán `first = new Box("Fresh", 7)`, `old` tiếp tục giữ tham chiếu đối tượng cũ.
6. `final Box fixedReference = old` ngăn gán lại biến `fixedReference`; nó **không** đóng băng `points` bên trong đối tượng. Thay field qua `fixedReference` làm `old.points` thành 30.
7. `absent.points` gây `NullPointerException` vì `absent` là `null`. Mảng `Box[]` cũng là đối tượng; mỗi phần tử tham chiếu ban đầu là `null`. Gán `slots[0] = old` tạo thêm một alias.

## 3. Java luôn truyền tham số **theo giá trị**

Với tham số kiểu tham chiếu, Java **sao chép giá trị tham chiếu** vào biến tham số. Vì vậy cần tách hai việc:

~~~java
static void mutate(Box b) {
    b.points = 42; // Sua trang thai doi tuong chung.
}

static void reassign(Box b) {
    b = new Box("Other", 42); // Chi gan lai tham so b.
}
~~~

- Gọi `mutate(first)` có thể khiến `first.points` thay đổi, vì bên gọi và tham số đều dẫn tới cùng đối tượng.
- Gọi `reassign(first)` **không** làm biến `first` trỏ tới một đối tượng mới.
- Nếu muốn bên gọi dùng một đối tượng thay thế, phương thức có thể **trả về tham chiếu mới**, rồi bên gọi viết `first = createReplacement(...);`.

Không gọi cơ chế này là “Java truyền tham chiếu theo tham chiếu”: **Java không cho phương thức gán lại biến tham chiếu của bên gọi bằng cách gán lại tham số**.


## 4. Nhận diện cùng đối tượng

Hai lần `new Box("A", 10)` tạo hai đối tượng có thể cùng dữ liệu, nhưng `x == y` sẽ là `false` nếu `x` và `y` trỏ tới hai đối tượng ấy. Ngược lại, `Box z = x;` khiến `x == z` là `true` vì chỉ sao chép tham chiếu. `==` không tự so các field; với `String`, dùng `equals` khi muốn so nội dung. Kiểu tự định nghĩa chỉ so giá trị bằng `equals` khi có hợp đồng phù hợp.


## 5. Giá trị `null` và biến chưa gán

`Box absent = null;` là biến đã có giá trị nhưng chưa chỉ tới đối tượng nào; `absent.points` sẽ ném `NullPointerException`. Ngược lại, biến cục bộ chỉ mới khai báo `Box pending;` chưa được *definite assignment* nên không được đọc. Field và phần tử mảng kiểu tham chiếu có giá trị mặc định `null`.

`alias = null` chỉ thay giá trị một biến, không hủy đối tượng đang được các alias khác giữ; thời điểm garbage collector thu hồi không được bảo đảm. Đóng tài nguyên như file hoặc socket theo `close()`/`try-with-resources` là trách nhiệm riêng.

## 6. Những nhận định dễ sai

| Nhận định | Đúng/sai | Giải thích |
| --- | --- | --- |
| “`Box b = a;` tạo Box mới.” | **Sai** | Chỉ sao chép giá trị tham chiếu |
| “Hai biến trỏ cùng đối tượng, sửa field qua biến này sẽ thấy qua biến kia.” | **Đúng** với field có thể sửa | Cả hai truy cập cùng trạng thái |
| “Gán `b = null` sẽ xóa đối tượng ngay.” | **Sai** | Chỉ đổi tham chiếu; có thể còn alias khác |
| “`new Box(1)` và `new Box(1)` là cùng đối tượng.” | **Sai** | Hai lần tạo đối tượng riêng |
| “Gán lại tham số kiểu `Box` sẽ đổi biến bên gọi.” | **Sai** | Tham số là bản sao của giá trị tham chiếu |
| “`final Box b` làm mọi field bất biến.” | **Sai** | `final` ràng buộc gán lại biến, không tự ràng buộc trạng thái đối tượng |
| “`null` là một đối tượng rỗng.” | **Sai** | Không có đối tượng nào được tham chiếu |
| “Mảng `Box[]` chứa sẵn các `Box` được `new` riêng.” | **Sai** | Các phần tử kiểu tham chiếu ban đầu là `null` |

## 7. Bài tập tự kiểm tra

**Bài 1.** Dự đoán kết quả sau:

~~~java
Box a = new Box("One", 1);
Box b = a;
b.points = 4;
System.out.println(a.points);
~~~

*Đáp án:* `4`. Hai biến cùng tham chiếu một đối tượng.

**Bài 2.** Nếu tiếp tục viết `b = new Box("Two", 9);`, `a.points` thành bao nhiêu?

*Đáp án:* Vẫn là `4`. Chỉ `b` trỏ sang đối tượng mới.

**Bài 3.** Với `Box x = null;`, kiểm tra `x == null` có hợp lệ không? Còn `x.points`?

*Đáp án:* Phép so sánh hợp lệ và trả `true`. Truy cập field ném `NullPointerException`.

**Bài 4.** Tại sao một phương thức nhận `Box parameter` rồi viết `parameter = new Box("New", 3);` không sửa tham chiếu trong biến của bên gọi?

*Đáp án:* Java truyền **bản sao giá trị tham chiếu** vào tham số; phép gán chỉ cập nhật tham số cục bộ.

**Bài 5.** `final Box b = new Box("Fixed", 5);` có cho phép `b.points = 6;` không? Có cho phép `b = new Box("Other", 6);` không?

*Đáp án:* Cho phép thay đổi `points`; không cho phép gán lại biến `final`.

## Checklist

- [ ] Phân biệt **biến tham chiếu** với **đối tượng được tạo**.
- [ ] Hiểu phép gán giữa biến tham chiếu là **sao chép giá trị tham chiếu**.
- [ ] Phân biệt sửa field của đối tượng với gán lại biến trỏ sang đối tượng khác.
- [ ] Biết `==` so sánh đồng nhất đối tượng, không mặc định so nội dung.
- [ ] Biết Java truyền mọi tham số theo giá trị, kể cả tham số là tham chiếu.
- [ ] Hiểu `null`, truy cập qua `null` và điều kiện thu gom bộ nhớ.
- [ ] Không hiểu nhầm `final` là làm đối tượng bất biến.

**Ghi nhớ:** Một biến tham chiếu là **nơi giữ đường dẫn logic tới đối tượng**, còn đối tượng là **thực thể chứa trạng thái**. Sao chép đường dẫn không sao chép thực thể; sửa thực thể không tự thay biến; thay biến không tự sửa hay xóa thực thể.
