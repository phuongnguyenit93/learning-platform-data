# Khai báo biến không đồng nghĩa với tạo đối tượng — Java 17+

Trong Java, **khai báo một biến tham chiếu** không đồng nghĩa với **tạo một đối tượng**. Đây là hai hành động độc lập: biến giữ một **giá trị tham chiếu** (hoặc `null`), còn đối tượng là thực thể được tạo ra khi một thao tác thực sự khởi tạo đối tượng.

~~~java
Book book;                    // Chi khai bao bien cuc bo, chua tao Book.
book = null;                 // Bien khong tham chieu den doi tuong nao.
book = new Book("Java");     // Tao Book, gan tham chieu cho book.
Book alias = book;           // Sao chep tham chieu, KHONG tao Book moi.
~~~

Không thể đọc `book` ngay sau dòng `Book book;` nếu đó là biến cục bộ: nó chưa được gán chắc chắn (*definite assignment*). Ngược lại, field kiểu tham chiếu của lớp/đối tượng chưa được khởi tạo tường minh sẽ có giá trị mặc định `null`.

## 1. Phân biệt các thao tác

| Đoạn mã | Điều gì xảy ra? | Có tạo `Book` mới? |
| --- | --- | --- |
| `Book a;` | Khai báo biến cục bộ chưa gán | **Không** |
| `Book a = null;` | Khai báo và gán tham chiếu null | **Không** |
| `Book a = new Book("A");` | Gọi constructor của một Book mới | **Có** |
| `Book b = a;` | Sao chép tham chiếu, tạo alias | **Không** |
| `a = new Book("B");` | Gán lại biến `a` để trỏ tới Book mới | **Có** |
| `Book[] books = new Book[2];` | Tạo **một đối tượng mảng**, hai phần tử ban đầu là null | **Không tạo Book** |
| `books[0] = a;` | Đặt tham chiếu sẵn có vào phần tử mảng | **Không** |

**Cần phân biệt loại đối tượng được tạo:** `new Book[2]` vẫn tạo **đối tượng mảng `Book[]`**, nhưng không gọi constructor `Book` hai lần. Mỗi phần tử của mảng tham chiếu ban đầu bằng `null`.

Một đối tượng cũng có thể được truy cập qua giá trị mà một phương thức trả về, một field, hoặc một biến khác. Đừng hiểu nhầm rằng **mỗi tên biến** đều phải đi với một **đối tượng riêng**.

## 2. Chương trình Java 17+ runnable

Tạo file UTF-8 tên **`DeclarationAndCreationDemo.java`**:

~~~java
public class DeclarationAndCreationDemo {
    static class Book {
        static int constructed;
        final String title;

        Book(String title) {
            this.title = title;
            constructed++;
        }
    }

    static class Shelf {
        Book current; // Reference field mac dinh null.
    }

    static Book shared; // Static reference field mac dinh null.

    public static void main(String[] args) {
        Book pending;
        pending = null;
        System.out.println("pendingNull=" + (pending == null));
        System.out.println("constructedStart=" + Book.constructed);

        Shelf shelf = new Shelf(); // Tao Shelf, KHONG tao Book.
        System.out.println("shelfBookNull=" + (shelf.current == null));
        System.out.println("sharedNull=" + (shared == null));

        Book first = new Book("Java");
        System.out.println("afterFirst=" + Book.constructed);

        Book alias = first; // Khong new, khong goi constructor.
        System.out.println("afterAlias=" + Book.constructed);
        System.out.println("aliasSame=" + (alias == first));

        Book second = new Book("Java");
        System.out.println("afterSecond=" + Book.constructed);
        System.out.println("sameObject=" + (first == second));
        System.out.println("sameTitle=" + first.title.equals(second.title));

        Book[] slots = new Book[2];
        System.out.println("afterArray=" + Book.constructed);
        System.out.println("firstSlotNull=" + (slots[0] == null));

        slots[0] = first;
        shelf.current = first;
        shared = second;
        System.out.println("slotAlias=" + (slots[0] == first));
        System.out.println("shelfAlias=" + (shelf.current == first));
        System.out.println("sharedSecond=" + (shared == second));

        first = second;
        System.out.println("firstNowSecond=" + (first == second));
        System.out.println("aliasStillOld=" + (alias == slots[0]));
        System.out.println("constructedEnd=" + Book.constructed);

        try {
            System.out.println(pending.title);
        } catch (NullPointerException ex) {
            System.out.println("nullAccess=NullPointerException");
        }
    }
}
~~~

Tại thư mục chứa file, mở PowerShell hoặc Bash và dùng **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 DeclarationAndCreationDemo.java
java DeclarationAndCreationDemo
~~~

**Expected output** của lệnh `java DeclarationAndCreationDemo` (không tính thông tin phiên bản JDK):

~~~text
pendingNull=true
constructedStart=0
shelfBookNull=true
sharedNull=true
afterFirst=1
afterAlias=1
aliasSame=true
afterSecond=2
sameObject=false
sameTitle=true
afterArray=2
firstSlotNull=true
slotAlias=true
shelfAlias=true
sharedSecond=true
firstNowSecond=true
aliasStillOld=true
constructedEnd=2
nullAccess=NullPointerException
~~~

### Giải thích kết quả

- `Book pending;` không tạo `Book`. Sau khi gán `pending = null`, biến đã được khởi tạo hợp lệ, nhưng vẫn không tham chiếu đối tượng.
- `new Shelf()` **tạo một Shelf** chứ không tạo sẵn Book. Field `current` trong Shelf và field `shared` mặc định là `null`.
- Mỗi biểu thức `new Book("Java")` gọi constructor `Book` một lần. Trong chương trình, `Book.constructed` tăng từ 0 lên 1 rồi 2.
- `Book alias = first;` **không gọi constructor**. Hai biến cùng tham chiếu một Book; `alias == first` là `true`.
- `first` và `second` là hai Book riêng biệt dù `title.equals` cho `true`. `==` với hai tham chiếu ở đây so sánh **đồng nhất đối tượng**, không so sánh nội dung.
- `new Book[2]` chỉ tạo **một mảng**. Hai ô của mảng nhận giá trị null, không tự nhận Book. Vì vậy `afterArray=2`.
- Gán `slots[0] = first`, `shelf.current = first` và `shared = second` chỉ lưu **các tham chiếu sẵn có**.
- `first = second` không xóa Book cũ. `alias` và `slots[0]` vẫn tham chiếu Book cũ; không có constructor được gọi thêm.
- `pending.title` cố truy cập field qua `null`, gây `NullPointerException` và được chương trình bắt để in thông báo xác định.

**Lưu ý:** `constructed` chỉ là bộ đếm *lần gọi constructor Book trong ví dụ một luồng*. Nó không phải bộ đếm tất cả object trong JVM: còn có đối tượng Shelf, đối tượng mảng và các đối tượng khác.

## 3. Biến chưa gán, biến `null` và đối tượng thật

~~~java
Book local;             // Khai bao local; CHUA duoc gan.
// System.out.println(local); // Loi bien dich: chua definite assignment.

local = null;           // Da gan, nhung khong co doi tuong.
System.out.println(local == null); // true.

local = new Book("A");  // Bay gio co doi tuong Book.
System.out.println(local.title);   // A.
~~~

Có ba trạng thái cần tách biệt:

1. **Biến cục bộ chưa được gán chắc chắn:** compiler **không cho phép đọc** giá trị.
2. **Biến đã gán `null`:** đọc chính biến hợp lệ, nhưng gọi phương thức hoặc đọc field qua nó sẽ ném `NullPointerException`.
3. **Biến trỏ tới một đối tượng:** có thể truy cập thành viên của đối tượng đó theo quyền truy cập và trạng thái thực tế.

Field của lớp/đối tượng khác local variable: `Book field;` ở cấp lớp nhận giá trị mặc định `null`. Nhưng **null không phải là một đối tượng Book rỗng**. `new Book("")` tạo Book thật, còn `Book b = null;` thì không.


## 4. Biến có thể lấy tham chiếu từ nhiều nguồn

Sau `Book alias = first;`, cả hai biến giữ tham chiếu tới cùng một `Book`; gán `slots[0] = first` cũng không tạo `Book` mới. `Book shared = getBook();` nhận giá trị trả về của phương thức, còn field và tham số cũng có thể giữ tham chiếu đã có. Vì vậy **đếm biến hoặc phép gán không cho biết số đối tượng được tạo**; trong ví dụ chạy, bộ đếm constructor mới giúp theo dõi riêng các instance `Book`.


## 5. `final` có tạo hoặc bảo toàn đối tượng không?

`final Book b;` chỉ khai báo một biến chưa được gán ở phạm vi cục bộ. Nó chưa tạo `Book` và vẫn phải được gán chắc chắn trước khi đọc; sau lần gán hợp lệ, biến `final` không thể được gán lại. Bỏ tham chiếu bằng cách gán `null` ở biến khác cũng không hủy đối tượng ngay: một alias vẫn có thể dùng nó. Các điều này đều độc lập với việc constructor đã được gọi bao nhiêu lần.


## 6. Tự phân biệt các trường hợp dễ nhầm

| Mã | Có tạo `Book` mới? | Vì sao? |
| --- | --- | --- |
| `Book a;` hoặc `Book a = null;` | Không | Chỉ khai báo/gán biến |
| `Book b = a;` | Không | Sao chép tham chiếu |
| `new Book[2]` | Không | Tạo một **mảng** chứ không tạo `Book` |
| `Book b = new Book("X");` | Có | Một lần khởi tạo `Book` |
| `b = new Book("Y");` | Có | Khởi tạo thêm `Book` rồi gán lại `b` |

Đối tượng còn có thể đến từ lời gọi phương thức hoặc literal; không phải mọi tham chiếu đều được tạo tại dòng khai báo biến.

## 7. Bài tập tự kiểm tra

**Bài 1.** Bao nhiêu đối tượng `Book` được tạo?

~~~java
Book a = new Book("X");
Book b = a;
Book c = null;
~~~

*Đáp án:* **Một Book**. `b` chỉ là alias, `c` là null.

**Bài 2.** `Book[] a = new Book[3];` tạo bao nhiêu mảng và bao nhiêu Book?

*Đáp án:* Một **mảng Book[]**, **không có Book** mới; các phần tử đều null.

**Bài 3.** Tại sao `Book x; System.out.println(x);` ở trong phương thức không biên dịch?

*Đáp án:* `x` là biến cục bộ chưa được gán chắc chắn (*definite assignment*).

**Bài 4.** `Book x = new Book("One"); Book y = x; x = new Book("Two");`. `y` trỏ đối tượng nào?

*Đáp án:* Vẫn là Book “One”, còn `x` trỏ Book “Two”.

**Bài 5.** `Book x = null;` có tương đương `Book x = new Book("");` không?

*Đáp án:* Không. Câu đầu không tạo object; câu sau tạo một Book với `title` là chuỗi rỗng.

## Checklist

- [ ] Phân biệt **khai báo biến** với **tạo đối tượng**.
- [ ] Phân biệt local variable chưa gán với reference có giá trị null.
- [ ] Biết phép gán tham chiếu tạo **alias**, không nhân bản object.
- [ ] Biết mảng tham chiếu là **đối tượng mảng**, các phần tử ban đầu null.
- [ ] Biết gán lại biến không thay đổi các tham chiếu khác đến object cũ.
- [ ] Không dùng `==` để suy ra hai đối tượng có cùng nội dung.
- [ ] Không nghĩ `final` hay gán `null` sẽ tự tạo/xóa object.

**Ghi nhớ:** Một biến là **nơi giữ giá trị tham chiếu**; một đối tượng là **thực thể được tạo và có trạng thái**. Đếm số lần tạo đối tượng phù hợp, **không đếm tên biến**, khi phân tích chương trình Java.
