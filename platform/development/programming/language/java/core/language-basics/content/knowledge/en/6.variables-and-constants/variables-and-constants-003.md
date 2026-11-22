# Phân biệt biến cục bộ, tham số và trường trong Java 17+

Trong Java, ba khai báo có thể cùng dùng kiểu `int` nhưng có vai trò rất khác nhau:

- **Biến cục bộ (local variable):** khai báo bên trong thân phương thức, constructor hoặc khối; dùng để tính toán tạm trong phạm vi đó.
- **Tham số (parameter):** biến được khai báo trong phần tham số của phương thức/constructor; nhận giá trị do bên gọi truyền vào.
- **Trường (field):** biến khai báo ở cấp lớp hoặc interface, bên ngoài các phương thức; biểu diễn trạng thái của **đối tượng** hoặc dữ liệu **thuộc lớp** nếu là `static`.

Hiểu rõ nơi khai báo, phạm vi sử dụng và cách khởi tạo giúp tránh lỗi `cannot find symbol`, `variable might not have been initialized` và nhầm dữ liệu giữa các đối tượng.

## 1. Nhận diện nhanh bằng vị trí khai báo

~~~java
public class Example {
    private int balance;             // Instance field.
    private static int accountCount; // Static field.

    public Example(int initial) {    // initial: tham số constructor.
        int checked = initial >= 0 ? initial : 0; // Biến cục bộ.
        this.balance = checked;      // Gán vào field của đối tượng.
        accountCount++;
    }

    public int increase(int amount) { // amount: tham số phương thức.
        int next = balance + amount;  // next: biến cục bộ.
        balance = next;               // Cập nhật instance field.
        return balance;
    }
}
~~~

| Tiêu chí | Biến cục bộ | Tham số | Trường instance | Trường `static` |
| --- | --- | --- | --- | --- |
| Khai báo ở đâu? | Trong phương thức, constructor hoặc khối | Danh sách tham số | Trong thân lớp, không có `static` | Trong thân lớp, có `static` |
| Thuộc về ai? | Một lần thực thi/phạm vi thích hợp | Một lần gọi phương thức/constructor | Mỗi đối tượng có bản riêng | Gắn với lớp trong ngữ cảnh tải lớp |
| Có giá trị mặc định tự động? | **Không** | Không; nhận giá trị khi được gọi | **Có** | **Có** |
| Tồn tại/được truy cập theo phạm vi nào? | Phạm vi khai báo và quy tắc luồng điều khiển | Trong thân khai báo tương ứng | Qua đối tượng hoặc `this` | Qua tên lớp, ví dụ `Example.accountCount` |
| Điển hình dùng cho | Kết quả tính tạm | Input của thao tác | Trạng thái từng đối tượng | Đếm đối tượng, cấu hình dùng chung |

Tham số trong Java vẫn là **biến**, nhưng nó khác biến cục bộ tự khai báo ở chỗ **giá trị ban đầu được bên gọi cung cấp**. Nói “tham số là biến cục bộ” có thể đúng theo cách diễn giải rộng về vùng sử dụng, nhưng khi phân loại theo **vị trí khai báo** nên tách chúng ra.

## 2. Chương trình Java chạy được

Lưu file UTF-8 **`VariableKindsDemo.java`**:

~~~java
public class VariableKindsDemo {
    private static int accountCount;  // Static field: ban dau = 0.

    private final String owner;        // Instance field.
    private int balance;               // Instance field: ban dau = 0.
    private boolean active;            // Instance field: ban dau = false.

    public VariableKindsDemo(String owner) {
        this.owner = owner;            // Field = tham so cung ten.
        accountCount++;
    }

    public void deposit(int amount) {  // amount: tham so.
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        int before = balance;          // Bien cuc bo.
        balance += amount;             // Cap nhat instance field.
        System.out.println(owner + ": " + before + " -> " + balance);
    }

    public static void main(String[] args) {
        int startingAmount = 50;       // Bien cuc bo cua main.

        VariableKindsDemo mai = new VariableKindsDemo("Mai");
        VariableKindsDemo an = new VariableKindsDemo("An");

        System.out.println("accounts=" + accountCount);
        System.out.println("mai.initialBalance=" + mai.balance);
        System.out.println("mai.initialActive=" + mai.active);

        mai.deposit(startingAmount);
        an.deposit(20);

        System.out.println("mai.finalBalance=" + mai.balance);
        System.out.println("an.finalBalance=" + an.balance);
        System.out.println(
                "accounts.shared=" + VariableKindsDemo.accountCount);
    }
}
~~~

Mở **PowerShell trên Windows** hoặc **Bash trên Linux** ở thư mục chứa tệp:

~~~bash
java -version
javac -version
javac -encoding UTF-8 VariableKindsDemo.java
java VariableKindsDemo
~~~

**Expected output:**

~~~text
accounts=2
mai.initialBalance=0
mai.initialActive=false
Mai: 0 -> 50
An: 0 -> 20
mai.finalBalance=50
an.finalBalance=20
accounts.shared=2
~~~

Vì sao?

1. `accountCount` là **static field**, tăng mỗi lần constructor chạy; có hai đối tượng nên kết quả là 2, bất kể đọc qua `accountCount` hay `VariableKindsDemo.accountCount`.
2. `balance` và `active` là **instance fields** không khởi tạo tường minh: Java đặt giá trị mặc định `0` và `false` cho mỗi đối tượng.
3. `owner` cũng là instance field nhưng được gán trong constructor. Tham số `owner` chỉ dùng để cung cấp giá trị cho trường `this.owner`.
4. `startingAmount` là biến cục bộ của `main`; `mai.deposit(startingAmount)` truyền giá trị 50 vào tham số `amount` của `deposit`.
5. `before` là biến cục bộ **riêng trong từng lần gọi `deposit`**. Trường `balance` của Mai thay đổi thành 50, còn của An thành 20: hai đối tượng không dùng chung instance field.

`main` là phương thức `static`: ở đó bạn **không thể truy cập trực tiếp `balance`** nếu không thông qua đối tượng (ví dụ `mai.balance`). Ngược lại, các phương thức instance như `deposit` có thể truy cập trường instance thông qua `this` ngầm định.


## 3. Khởi tạo theo từng loại biến

**Field** có giá trị mặc định theo kiểu (`int` là 0, `boolean` là `false`, tham chiếu là `null`), dù field initializer và constructor có thể thay giá trị đó. **Tham số** nhận giá trị đối số từ lời gọi. **Biến cục bộ** không có giá trị mặc định được phép đọc; cần gán chắc chắn trước khi đọc.

~~~java
class ExampleState {
    int count; // 0 khi object mới tạo

    int sum(int input) { // input là tham số đã nhận giá trị từ caller
        int result = count + input; // result là local được khởi tạo
        return result;
    }
}
~~~

Một `final` instance field chưa có initializer phải được gán hợp lệ trước khi constructor hoàn tất bình thường, như `owner` trong ví dụ chính. Bài về giá trị mặc định giải thích đầy đủ kiểu mảng, `char`, wrapper và thứ tự khởi tạo; bài về *definite assignment* phân tích các nhánh điều khiển.

## 4. Phạm vi (scope) và tên bị che (shadowing)

Biến cục bộ hoặc tham số có thể **che** field cùng tên. Trong ví dụ:

~~~java
private final String owner;

public VariableKindsDemo(String owner) {
    this.owner = owner;
}
~~~

- `owner` bên phải là **tham số** constructor.
- `this.owner` bên trái là **field** của đối tượng hiện tại.

Nếu chỉ viết `owner = owner;`, cả hai vế sẽ nói tới tham số, không gán cho field; với field `final` chưa được khởi tạo, constructor còn vi phạm yêu cầu gán giá trị bắt buộc.

**Phạm vi khối:** biến khai báo trong `{ ... }` không dùng được ở ngoài phạm vi của nó:

~~~java
if (true) {
    int inside = 10;
    System.out.println(inside);
}
// System.out.println(inside); // Loi: khong thay ten inside.
~~~

Không chỉ có thụt lề: **dấu ngoặc nhọn và vị trí khai báo** mới quyết định phạm vi hợp lệ. Hai biến cục bộ cùng tên ở những phạm vi lồng nhau cũng không thể tùy ý được khai báo chồng lên nhau; khi không chắc, dùng tên rõ nghĩa thay vì cố tạo nhiều tên trùng.

## 5. Truyền tham số trong Java là truyền theo giá trị

Java **luôn truyền giá trị** vào tham số:

~~~java
static void changeNumber(int value) {
    value = 99; // Chi doi bien tham so.
}

// Trong main:
int number = 5;
changeNumber(number);
System.out.println(number); // 5
~~~

Đối với kiểu nguyên thủy, giá trị số được sao chép. Đối với đối tượng, **giá trị tham chiếu** được sao chép; phương thức có thể thay đổi trạng thái của đối tượng chung thông qua tham chiếu đó (nếu đối tượng cho phép), nhưng gán lại biến tham số không tự đổi tham chiếu trong biến của bên gọi.

Đừng diễn giải “tham số lưu ở stack, field lưu ở heap” thành một quy luật vật lý tuyệt đối: cách tối ưu hóa bộ nhớ là chi tiết triển khai của JVM. Khi học ngôn ngữ, quan trọng hơn là **ngữ nghĩa, phạm vi và cách chia sẻ trạng thái**.

## 6. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `variable might not have been initialized` | Đọc biến cục bộ trước khi gán chắc chắn | Gán giá trị trên mọi nhánh cần thiết |
| `cannot find symbol` với biến | Dùng ngoài phạm vi hoặc gõ sai tên | Xem nơi khai báo và cặp `{ }` |
| `non-static variable ... cannot be referenced from a static context` | Đọc instance field trực tiếp trong `main` | Tạo/nhận đối tượng rồi truy cập qua đối tượng |
| Field không thay đổi sau constructor | Tham số che tên field, viết `owner = owner` | Viết `this.owner = owner` |
| Hai đối tượng có chung giá trị ngoài dự kiến | Dùng `static` cho dữ liệu đáng ra thuộc từng đối tượng | Bỏ `static` với trạng thái riêng |
| Field luôn bằng 0 hoặc `null` | Quên khởi tạo hoặc quên gán đúng field | Kiểm tra constructor và initializer |
| Gán lại tham số nhưng bên gọi không đổi | Java truyền giá trị của đối số | Trả kết quả rồi gán ở bên gọi nếu cần |

## 7. Bài tập tự kiểm tra

1. **Phân loại:** Trong `VariableKindsDemo`, `accountCount`, `owner`, `balance`, `startingAmount`, `amount`, `before` thuộc nhóm nào?  
   *Đáp án:* `accountCount` là static field; `owner` và `balance` là instance fields; `startingAmount` và `before` là local variables; `amount` là parameter. Ngoài ra còn có tham số constructor `owner` che tên field.
2. **Dự đoán:** Nếu gọi `mai.deposit(10)` thêm một lần, `mai.balance` và `an.balance` là bao nhiêu?  
   *Đáp án:* 60 và 20. `accountCount` vẫn 2 vì không tạo thêm đối tượng.
3. **Khởi tạo:** Tại sao `int balance;` ở cấp lớp đọc ra 0, nhưng `int local; System.out.println(local);` trong phương thức không biên dịch?  
   *Đáp án:* Field nhận giá trị mặc định; local cần được gán chắc chắn.
4. **Shadowing:** Giải thích khác biệt giữa `this.owner = owner;` và `owner = owner;` trong constructor.  
   *Đáp án:* Câu đầu gán tham số cho field; câu sau chỉ gán tham số cho chính nó.
5. **Truyền giá trị:** Vì sao đổi tham số `value` trong `changeNumber` không đổi biến `number` bên gọi?  
   *Đáp án:* Tham số giữ bản sao của giá trị số.

## Checklist

- [ ] Nhận diện được **biến cục bộ**, **tham số**, **instance field**, **static field** theo vị trí khai báo.
- [ ] Biết field có giá trị mặc định nhưng local variable thì không.
- [ ] Dùng `this.field` để giải quyết tên bị tham số hoặc biến cục bộ che.
- [ ] Không dùng local variable ngoài phạm vi khối.
- [ ] Hiểu instance field thuộc từng đối tượng, static field dùng chung ở cấp lớp.
- [ ] Giải thích được cách Java truyền giá trị vào tham số.
- [ ] Biên dịch và chạy `VariableKindsDemo.java`, dự đoán chính xác tám dòng kết quả.

**Ghi nhớ:** Biến cục bộ phục vụ một đoạn tính toán, tham số mang dữ liệu của lời gọi, còn trường lưu trạng thái của đối tượng hoặc lớp. Hãy hỏi ba câu khi gặp một tên biến: **Nó khai báo ở đâu? Ai sở hữu giá trị đó? Và khi nào nó được gán?**
