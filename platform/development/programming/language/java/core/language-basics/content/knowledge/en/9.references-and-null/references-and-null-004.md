# Gán tham chiếu làm nhiều biến cùng dùng một đối tượng trong Java

> **Java core — language-basics / Tham chiếu và null**  
> **Yêu cầu:** JDK 17+; dùng thư viện chuẩn, một file Java chạy độc lập.  
> **Mục tiêu:** Hiểu phép gán giữa các biến kiểu tham chiếu **sao chép giá trị tham chiếu**, không sao chép object; phân biệt **sửa trạng thái object** với **gán lại biến** và biết cách hạn chế tác dụng phụ do nhiều biến cùng trỏ tới một object.

## 1. Biến tham chiếu không chứa một bản sao của object

Ví dụ:

~~~java
class Box {
    int value;
    Box(int value) {
        this.value = value;
    }
}

Box first = new Box(10);
Box second = first;
~~~

Dòng `new Box(10)` tạo một object `Box`. Biến `first` giữ tham chiếu đến object ấy. Dòng `second = first` **sao chép giá trị tham chiếu** sang `second` — không gọi `new` và **không tạo bản sao**.

Sau phép gán, hai tên cùng trỏ đến **một object**:

~~~mermaid
flowchart LR
    A["first"] --> O["Box object: value = 10"]
    B["second"] --> O
~~~

Cách hình dung: `first` và `second` là **hai biến riêng**, nhưng lúc này giá trị của hai biến là tham chiếu tới **cùng một đối tượng**. Các biến không trỏ tới nhau.

| Thao tác | Object có được tạo mới? | Điều xảy ra |
| --- | --- | --- |
| `Box first = new Box(10);` | Có | Tạo Box và lưu tham chiếu trong first |
| `Box second = first;` | Không | Hai biến trỏ chung một Box |
| `second.value = 20;` | Không | Sửa Box chung, đọc `first.value` cũng được 20 |
| `second = new Box(30);` | Có | second đổi sang Box mới; first vẫn trỏ Box cũ |
| `second = null;` | Không | Chỉ second không trỏ tới object nào; first không đổi |

**Điểm cốt lõi:** `second = first` không phải *deep copy*, *shallow copy object* hay phép sao chép toàn bộ dữ liệu. Đây là **gán tham chiếu**.


## 2. Theo dõi một alias khi trạng thái thay đổi

Nếu `Box b = a;` rồi `b.value = 20;`, cả hai biến vẫn tham chiếu một object và `a.value` thành `20`. Nếu tiếp tục `b = new Box(30);`, chỉ `b` đổi sang object mới, `a.value` vẫn là `20`. Hai tình huống này khác nhau vì thao tác thứ nhất sửa **object chia sẻ**, thao tác thứ hai sửa **giá trị tham chiếu trong biến**. Trong ví dụ đầy đủ sau, hãy theo dõi các nhánh alias của object gốc thay vì chỉ nhìn tên biến.

## 3. Ví dụ Java 17+ runnable

Tạo tệp **ReferenceAliasDemo.java**:

~~~java
public final class ReferenceAliasDemo {
    private static final class Box {
        private int score;

        Box(int score) {
            this.score = score;
        }

        void add(int amount) {
            score += amount;
        }

        int getScore() {
            return score;
        }
    }

    private static void addPoints(Box box) {
        box.add(5); // Sửa chính object mà bên gọi đang giữ.
    }

    private static void rebind(Box box) {
        box = new Box(999); // Chỉ đổi biến tham số cục bộ.
        System.out.println("insideRebind=" + box.getScore());
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;

        System.out.println("sameReference=" + (first == alias));

        alias.add(10);
        System.out.println("viaFirst=" + first.getScore());

        addPoints(first);
        System.out.println("viaAlias=" + alias.getScore());

        rebind(alias);
        System.out.println("afterCall=" + alias.getScore());

        alias = new Box(30);
        System.out.println("sharedAfterRebind=" + (first == alias));
        System.out.println("firstScore=" + first.getScore());
        System.out.println("aliasScore=" + alias.getScore());

        Box third = first;
        third = null;
        System.out.println("thirdNull=" + (third == null));
        System.out.println("firstStill=" + first.getScore());

        int[] left = {1, 2};
        int[] right = left;
        right[0] = 9;
        System.out.println("arrayFirst=" + left[0]);

        String textA = "Hi";
        String textB = textA;
        textB = textB.concat("!");
        System.out.println("textA=" + textA);
        System.out.println("textB=" + textB);

        Box independent = new Box(first.getScore());
        independent.add(100);
        System.out.println("separateCopy=" + independent.getScore());
        System.out.println("originalStill=" + first.getScore());
    }
}
~~~

Biên dịch và chạy tại thư mục có file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ReferenceAliasDemo.java
java ReferenceAliasDemo
~~~

**Expected output (chính xác):**

~~~text
sameReference=true
viaFirst=20
viaAlias=25
insideRebind=999
afterCall=25
sharedAfterRebind=false
firstScore=25
aliasScore=30
thirdNull=true
firstStill=25
arrayFirst=9
textA=Hi
textB=Hi!
separateCopy=125
originalStill=25
~~~

**Giải thích các mốc quan trọng:**

1. `alias = first` làm `first == alias` là `true`.
2. Gọi `alias.add(10)` tăng object chung từ 10 lên 20; đọc qua `first` thấy 20. `addPoints(first)` tăng tiếp thành 25; đọc qua `alias` vẫn thấy 25.
3. Bên trong `rebind`, tham số `box` được gán sang Box mới (999). Khi phương thức trở về, `alias` của bên gọi vẫn trỏ Box điểm 25.
4. `alias = new Box(30)` làm `first` và `alias` trỏ **hai Box khác nhau**, có điểm lần lượt 25 và 30.
5. Gán `third = null` chỉ thay đổi biến `third`, không xóa Box được `first` giữ.
6. Mảng cũng là object: `right = left` làm hai biến dùng chung mảng; sửa `right[0]` thì `left[0]` thành 9.
7. `String` bất biến: `concat` tạo kết quả chuỗi `"Hi!"`, còn `textA` vẫn là `"Hi"`.
8. `new Box(first.getScore())` tạo Box riêng có giá trị ban đầu 25; tăng bản riêng thành 125 không đổi Box của `first`.


## 4. Alias được truyền qua tham số

Java truyền **theo giá trị**: method nhận bản sao tham chiếu. Vì thế `box.add(5)` có thể sửa object mà caller cũng giữ, còn `box = new Box(100)` chỉ gán lại tham số của method. Đây cũng là lý do `rebind(alias)` trong chương trình chỉ in `insideRebind=999` mà `alias` của caller vẫn có điểm `25`.


## 5. Aliasing không đồng nghĩa mọi dữ liệu đều sửa được

Mảng cũng là đối tượng có thể sửa: sau `int[] b = a; b[0] = 9;`, đọc `a[0]` được `9`. Trái lại, `String` bất biến; `String b = a; b = b.concat("!");` chỉ đổi tham chiếu của `b` sang kết quả, không sửa chuỗi mà `a` giữ. Gán `b = null` chỉ bỏ alias ở `b`, và biến `final` chỉ cấm gán lại chính nó; hai quy tắc này không làm object gốc biến mất hay bất biến.

## 6. Khi nào cần sao chép đối tượng?

Dùng chung tham chiếu hữu ích khi nhiều nơi **cố ý chia sẻ cùng trạng thái**. Nhưng nếu một nơi cần sửa mà không ảnh hưởng nơi khác, phải tạo **object độc lập**.

~~~java
Box original = new Box(10);
Box shared = original;                  // Cùng object.
Box independent = new Box(original.getScore()); // Object mới.
~~~

`independent.add(5)` không sửa `original` trong ví dụ Box chỉ có trường primitive `score`. Tuy nhiên, với object chứa tham chiếu tới các object mutable lồng bên trong, chỉ sao chép các field là **shallow copy** và có thể vẫn chia sẻ đối tượng con. Khi yêu cầu độc lập hoàn toàn, cần cân nhắc **deep copy** phù hợp với mô hình dữ liệu.

Với mảng primitive, `int[] copy = originalArray.clone();` tạo mảng mới với các giá trị độc lập. Với mảng các tham chiếu, `clone()` tạo **mảng mới**, nhưng các phần tử tham chiếu vẫn có thể trỏ tới **cùng object con**. Không áp dụng “clone = deep copy” cho mọi kiểu.

## 7. Lỗi thường gặp và câu hỏi tự kiểm tra

| Hiểu lầm | Sửa lại cho đúng |
| --- | --- |
| “`b = a` sẽ copy toàn bộ object.” | Sai: chỉ sao chép **giá trị tham chiếu**, không tạo object mới |
| “Sửa `b.score` không ảnh hưởng `a` vì là hai biến.” | Nếu `a == b` thì sửa cùng object, a nhìn thấy thay đổi |
| “`b = new Box(...)` làm `a` cũng đổi object.” | Sai: chỉ biến b được gán lại |
| “Gán `b = null` sẽ xóa object đang dùng chung.” | Sai: alias khác vẫn có thể tham chiếu object ấy |
| “Java pass-by-reference nên method đổi tham số sẽ đổi biến bên gọi.” | Sai: Java pass-by-value, sao chép giá trị tham chiếu |
| “Mảng gán bằng `=` sẽ tự sao chép các phần tử.” | Sai: hai biến cùng tham chiếu đến mảng cũ |
| “`String.concat` sửa nội dung String đang được chia sẻ.” | Sai: String bất biến; kết quả concat không sửa object gốc |

**Bài tập 1:** Cho `Box x = new Box(2); Box y = x;`. Dự đoán kết quả nếu gọi `y.add(3)` rồi đọc `x.getScore()`. `x == y` là true hay false?

**Bài tập 2:** Sau bài 1, thực hiện `y = new Box(10);`. Hỏi `x.getScore()` và `y.getScore()` bằng bao nhiêu; có bao nhiêu object Box đã được tạo?

**Bài tập 3:** Với `int[] a = {1, 2}; int[] b = a;`, hãy sửa `b[1]` thành 99 rồi in `a[1]`. Sau đó thử `b = a.clone(); b[1] = 5;`: kết quả `a[1]` có thay đổi tiếp không?

**Bài tập 4:** Viết phương thức nhận `Box` và thử hai thao tác: `box.add(1)`, `box = new Box(0)`. Giải thích vì sao chỉ một thao tác được bên gọi quan sát trên Box gốc.

**Bài tập 5:** Cho `String a = "Hi"; String b = a; b = b + "!";`. Dự đoán `a` và `b`, phân biệt **gán tham chiếu** với **tính bất biến của String**.

### Ghi nhớ

**Gán `b = a` với kiểu tham chiếu tạo thêm một alias tới cùng object, không sao chép object.** Mọi alias có thể nhìn thấy thay đổi **trạng thái object mutable**. Ngược lại, **gán lại biến** (sang object khác hoặc `null`) chỉ thay đổi biến ấy. Java truyền cả tham chiếu **theo giá trị**, và khi cần dữ liệu độc lập phải **tạo bản sao phù hợp**, không chỉ gán sang tên biến mới.
