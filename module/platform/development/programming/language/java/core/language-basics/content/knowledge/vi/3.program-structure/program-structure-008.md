# Thụt lề để thể hiện cấu trúc và tránh hiểu nhầm phạm vi trong Java

Khi đọc mã Java, **thụt lề (indentation)** giúp mắt người nhìn ra câu lệnh nào thuộc lớp, phương thức, nhánh `if` hoặc vòng lặp. Nhưng khác với một số ngôn ngữ lập trình, Java **không dùng độ thụt lề để quyết định phạm vi khối lệnh**. Dấu ngoặc nhọn `{ }` và cấu trúc cú pháp mới là căn cứ để trình biên dịch hiểu chương trình.

Vì vậy, một đoạn Java **có thể thụt lề rất đẹp mà vẫn làm sai ý định** nếu bạn bỏ dấu ngoặc nhọn. Bài học này giúp bạn đọc và viết các khối mã rõ ràng, hiểu phạm vi biến và phòng ngừa lỗi logic do bố cục gây hiểu nhầm. Ví dụ tương thích JDK 17 trở lên.

## 1. Quy tắc cốt lõi: thụt lề dành cho người đọc, ngoặc dành cho cú pháp

So sánh hai đoạn:

~~~java
int score = 4;

if (score >= 5) {
    System.out.println("Dat");
    System.out.println("Cap chung chi");
}
~~~

Với `score = 4`, **không dòng nào được in**: cả hai câu lệnh đều nằm trong khối `if`, điều kiện sai nên khối bị bỏ qua.

Nhưng nếu bỏ ngoặc nhọn:

~~~java
int score = 4;

if (score >= 5)
    System.out.println("Dat");
    System.out.println("Cap chung chi");
~~~

Kết quả:

~~~text
Cap chung chi
~~~

Java hiểu đoạn thứ hai tương đương:

~~~java
if (score >= 5) {
    System.out.println("Dat");
}
System.out.println("Cap chung chi");
~~~

Chỉ **một statement ngay sau `if`** được điều khiển khi không có khối `{ }`. Dòng `println` thứ hai luôn chạy, **bất kể nó được thụt vào bao nhiêu dấu cách**.

> Quy ước nên áp dụng: **luôn dùng `{ }` với `if`, `else`, `for` và `while`**, kể cả khi nhánh chỉ có một câu lệnh. Đây là quy ước giúp tránh lỗi, không phải yêu cầu cú pháp trong mọi trường hợp.

## 2. Cấu trúc lớp, phương thức và khối lệnh

Những mức thụt lề thường gặp khi đọc một tệp Java:

~~~java
public class LayoutExample {                  // Mức 0: lớp
    public static void main(String[] args) {  // Mức 1: phương thức
        int score = 8;                        // Mức 2: trong phương thức

        if (score >= 5) {                     // Mức 2: câu lệnh if
            System.out.println("Dat");        // Mức 3: trong khối if
        }

        System.out.println("Hoan tat");        // Mức 2: ngoài khối if
    }
}
~~~

Trên JDK 17, lưu đoạn trên vào `LayoutExample.java`, biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LayoutExample.java
java LayoutExample
~~~

Kết quả:

~~~text
Dat
Hoan tat
~~~

Hãy đọc dấu ngoặc trước khi đọc khoảng trắng:

| Dấu hiệu | Vai trò trong Java | Điều dễ nhầm |
| --- | --- | --- |
| `{` | Bắt đầu một khối, thân lớp hoặc thân phương thức tùy vị trí | Chỉ dựa vào cột thụt lề |
| `}` | Kết thúc khối tương ứng | Không nhận ra biến đã ra khỏi phạm vi |
| `;` | Kết thúc một số loại câu lệnh/khai báo | Đặt `;` sai ngay sau `if` |
| Khoảng trắng đầu dòng | Trình bày mã cho dễ đọc | Tưởng rằng tự tạo khối lệnh |
| `if` / `else` | Quyết định nhánh thực thi | Tưởng `else` luôn ghép với `if` có cùng độ thụt lề |
| `for` / `while` | Lặp một statement hoặc một khối | Tưởng tất cả dòng thụt vào đều lặp |

Trong mã nguồn, `{ }` phải ghép cặp đúng. Với editor hỗ trợ Java, đặt con trỏ lên một dấu ngoặc thường giúp nhìn thấy dấu còn lại.

## 3. Chương trình thực hành: thụt lề rõ để nhìn thấy phạm vi

Tạo tệp **`IndentScopeDemo.java`**:

~~~java
public class IndentScopeDemo {
    static String classify(int score) {
        if (score < 0 || score > 10) {
            throw new IllegalArgumentException(
                    "Diem phai nam trong khoang 0..10");
        }

        if (score >= 8) {
            return "Gioi";
        }

        if (score >= 5) {
            return "Dat";
        }

        return "Can co gang";
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println(
                    "Cach dung: java IndentScopeDemo <diem>");
            return;
        }

        try {
            int score = Integer.parseInt(args[0]);
            String result = classify(score);

            System.out.println("Diem: " + score);
            System.out.println("Xep loai: " + result);
            System.out.println("Hoan tat");
        } catch (NumberFormatException ex) {
            System.out.println("Loi: diem phai la so nguyen");
        } catch (IllegalArgumentException ex) {
            System.out.println("Loi: " + ex.getMessage());
        }
    }
}
~~~

### Chạy trên Windows PowerShell hoặc Linux

Tại thư mục chứa `IndentScopeDemo.java`, cả hai môi trường đều dùng được:

~~~bash
java -version
javac -version
javac -encoding UTF-8 IndentScopeDemo.java
java IndentScopeDemo 8
~~~

Kết quả:

~~~text
Diem: 8
Xep loai: Gioi
Hoan tat
~~~

Một trường hợp khác:

~~~bash
java IndentScopeDemo 4
~~~

~~~text
Diem: 4
Xep loai: Can co gang
Hoan tat
~~~

**Điểm cần chú ý:** câu lệnh `System.out.println("Hoan tat");` nằm sau khối phân loại và sau khi dữ liệu hợp lệ. Nó chạy với mọi điểm hợp lệ, không phụ thuộc vào nhánh `score >= 8` hoặc `score >= 5`.

Các `return` trong `classify` làm phương thức kết thúc ngay tại nhánh phù hợp. Vì thế, sau `return "Gioi";`, chương trình không tiếp tục kiểm tra `if (score >= 5)` trong **cùng lời gọi `classify`**.

**Bảng kiểm tra đầu vào:**

| Lệnh | Kết quả chính |
| --- | --- |
| `java IndentScopeDemo 10` | `Xep loai: Gioi` |
| `java IndentScopeDemo 8` | `Xep loai: Gioi` |
| `java IndentScopeDemo 7` | `Xep loai: Dat` |
| `java IndentScopeDemo 5` | `Xep loai: Dat` |
| `java IndentScopeDemo 4` | `Xep loai: Can co gang` |
| `java IndentScopeDemo 0` | `Xep loai: Can co gang` |
| `java IndentScopeDemo -1` | `Loi: Diem phai nam trong khoang 0..10` |
| `java IndentScopeDemo 11` | `Loi: Diem phai nam trong khoang 0..10` |
| `java IndentScopeDemo abc` | `Loi: diem phai la so nguyen` |
| `java IndentScopeDemo` | In hướng dẫn sử dụng |

Hai khối `catch` giúp tách lỗi **chuyển chuỗi sang số** khỏi lỗi **số ngoài khoảng hợp lệ**. `NumberFormatException` là lớp con của `IllegalArgumentException`, vì vậy nhánh bắt cụ thể phải đứng trước nhánh tổng quát.

## 4. Lỗi khó thấy: `else` thuộc về `if` nào?

Xem đoạn không dùng ngoặc:

~~~java
boolean registered = false;
int score = 3;

if (registered)
    if (score >= 5)
        System.out.println("Du dieu kien");
    else
        System.out.println("Chua dat diem");
~~~

Dù người viết có thể muốn `else` ứng với `if (registered)`, trong Java **`else` ghép với `if` gần nhất mà nó có thể ghép về mặt cú pháp**. Ở đây, `else` thuộc `if (score >= 5)`, và toàn bộ nhánh bên trong không chạy vì `registered` là `false`.

**Kết quả: không in dòng nào.**

Viết lại để ý định rõ ràng:

~~~java
boolean registered = false;
int score = 3;

if (registered) {
    if (score >= 5) {
        System.out.println("Du dieu kien");
    } else {
        System.out.println("Chua dat diem");
    }
} else {
    System.out.println("Chua dang ky");
}
~~~

**Kết quả:**

~~~text
Chua dang ky
~~~

Ngoặc nhọn không chỉ giúp đẹp mã: chúng **quy định chính xác các nhánh** mà lập trình viên muốn gắn với nhau.

## 5. Phạm vi biến (scope) không phụ thuộc vào độ thụt lề

Một biến cục bộ được khai báo trong khối thường chỉ dùng được ở phạm vi tương ứng:

~~~java
int score = 7;

if (score >= 5) {
    String message = "Dat";
    System.out.println(message); // Hợp lệ.
}

// System.out.println(message); // Không biên dịch:
// message đã ra khỏi phạm vi ở dấu } của if.
~~~

Muốn dùng kết quả ngoài khối, khai báo biến ở phạm vi phù hợp và gán giá trị bên trong:

~~~java
int score = 7;
String message;

if (score >= 5) {
    message = "Dat";
} else {
    message = "Can co gang";
}

System.out.println(message); // Dat
~~~

Compiler kiểm tra biến `message` đã được gán chắc chắn trước khi dùng (*definite assignment*). Việc tạo khoảng trắng hoặc thụt dòng `println` sang phải **không thể mở rộng phạm vi biến**.

Các dấu `{ }` có thể tạo khối độc lập bên trong phương thức:

~~~java
{
    int temporary = 5;
    System.out.println(temporary); // 5
}
// System.out.println(temporary); // Không thấy tên temporary ở đây.
~~~

Vì vậy, khi gặp lỗi `cannot find symbol` đối với biến cục bộ, hãy kiểm tra **cặp ngoặc và nơi khai báo biến**, không chỉ chỉnh số dấu cách.

## 6. Vòng lặp thiếu ngoặc cũng gây nhầm lẫn

Ví dụ:

~~~java
int i;
for (i = 0; i < 3; i++)
    System.out.println("Lan " + i);
    System.out.println("Ket thuc");
~~~

Dù hai dòng `println` có cùng độ thụt lề, vòng `for` chỉ điều khiển **lời gọi đầu tiên**. Kết quả:

~~~text
Lan 0
Lan 1
Lan 2
Ket thuc
~~~

Nếu muốn cả hai lời gọi chạy trong mỗi vòng lặp, đặt chúng trong khối:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println("Lan " + i);
    System.out.println("Ket thuc");
}
~~~

Khi đó `Ket thuc` được in **ba lần**, mỗi lần ngay sau `Lan i`. Đây là thay đổi logic do **ngoặc nhọn**, không phải do thêm khoảng trắng.

Tương tự với `while`, không có ngoặc thì chỉ statement ngay sau vòng lặp được lặp. Nếu statement đó không làm điều kiện tiến gần điểm dừng, chương trình có thể lặp vô hạn. Viết khối rõ ràng giúp nhìn thấy cả **điều kiện** lẫn **cập nhật biến điều khiển**.


## 7. Formatter làm lộ cấu trúc thật, nhưng không biết ý định của bạn

Formatter của IDE căn lề theo **cú pháp Java hiện có**. Nếu nó đưa một câu lệnh ra cấp ngoài của `if` hoặc `for`, đó là dấu hiệu nên đọc lại vị trí của `{` và `}`; formatter không tự biết bạn muốn câu lệnh ấy chỉ chạy trong nhánh hay chạy mọi lúc.

Khi review mã đã định dạng, hãy kiểm tra theo thứ tự:

1. **So các cặp ngoặc với ý định:** câu lệnh nào nằm trong block của lớp, phương thức, nhánh và vòng lặp?
2. **Đọc token quanh điều kiện:** một dấu `;` sau `if (...)` hoặc `while (...)` có thể tự tạo thân rỗng dù trình bày trông hợp lý.
3. **Thử hai đường đi:** chạy ca điều kiện đúng và sai, hoặc vòng lặp 0 và nhiều lần, rồi đối chiếu hành vi với mong đợi.

Ví dụ một câu `println` được formatter căn về cùng cấp với `if` sẽ vẫn nằm **ngoài** nhánh nếu ngoặc đóng trước nó. Muốn đổi hành vi phải sửa **vị trí ngoặc hoặc câu lệnh**, rồi kiểm thử lại; chỉ chỉnh khoảng trắng không đủ.

## 8. Quy tắc trình bày thực tế

Để mã Java 17 dễ đọc trong học tập và cộng tác:

1. **Thụt một mức thống nhất**, thường chọn **4 dấu cách** cho mỗi cấp khối; tránh trộn tab và spaces tùy tiện trong cùng tệp.
2. **Luôn dùng ngoặc nhọn** với câu lệnh điều kiện và vòng lặp, kể cả khối chỉ có một dòng.
3. Đặt ngoặc mở `{` cùng dòng khai báo `class`, phương thức hoặc `if` theo một phong cách nhất quán; đặt `}` ở cột tương ứng.
4. Không dùng thụt lề để “vẽ” phạm vi mà thiếu ngoặc thật.
5. Mỗi lần thêm hoặc chuyển một dấu ngoặc, biên dịch lại và chạy ca bình thường **và ca biên**.
6. Dùng trình định dạng Java tự động khi có, nhưng **đọc lại logic**: formatter không thể tự biết ý định nghiệp vụ của bạn.

Ví dụ bố cục dễ đọc:

~~~java
if (score >= 5) {
    System.out.println("Dat");
} else {
    System.out.println("Chua dat");
}
System.out.println("Hoan tat");
~~~

Đây là **quy ước trình bày**, không phải cú pháp thụt lề bắt buộc. Máy đọc cấu trúc nhờ từ khóa, dấu phân cách và khối; người đọc hưởng lợi từ cách trình bày phản ánh trung thực cấu trúc đó.

## 9. Bài tập tự kiểm tra

**Bài 1 — Dự đoán:** Với `score = 4`, đoạn `if (score >= 5) println("Dat"); println("Xong");` (hai statement riêng) sẽ in gì nếu dòng thứ hai được thụt vào dưới `if` nhưng không có ngoặc?

*Đáp án:* `Xong`. Chỉ statement thứ nhất phụ thuộc điều kiện.

**Bài 2 — Sửa nhánh:** Lấy ví dụ `registered` ở mục 4, thay thành `registered = true` và `score = 3`. Sau bản sửa có ngoặc, kết quả nào được in?

*Đáp án:* `Chua dat diem`.

**Bài 3 — Phạm vi:** Tại sao đặt `System.out.println(message);` sau khối `if` ở mục 5 lại không biên dịch? Sửa để chương trình in được message cho cả hai trường hợp điểm đạt và chưa đạt.

*Đáp án:* Biến khai báo trong khối đã ra khỏi phạm vi; khai báo trước `if` và gán ở cả `if` lẫn `else`.

**Bài 4 — Lặp:** Một bạn muốn in `Lan 0 - Xong`, `Lan 1 - Xong`, `Lan 2 - Xong`, mỗi lượt hai phần trên hai dòng. Hãy đặt lại `{ }` cho vòng `for` và dự đoán số lần in `Xong`.

*Đáp án:* Đặt cả hai `println` vào khối `for`; `Xong` được in ba lần.

**Bài 5 — Debug:** Chạy `java IndentScopeDemo 5`, rồi thử sửa điều kiện từ `score >= 5` thành `score > 5`. Điều gì thay đổi? Đó là lỗi thụt lề hay lỗi điều kiện?

*Đáp án:* Điểm 5 chuyển từ `Dat` thành `Can co gang`; đây là lỗi **logic điều kiện**, cho thấy mã thụt lề đúng vẫn có thể sai nghiệp vụ.

### Checklist cuối bài

- [ ] Giải thích được Java dựa vào `{ }` và cấu trúc cú pháp, không dựa vào độ sâu indentation để hiểu khối.
- [ ] Luôn dùng ngoặc nhọn khi viết `if`/`else` và vòng lặp.
- [ ] Nhận ra câu lệnh thứ hai không được điều khiển nếu `if` thiếu khối.
- [ ] Hiểu `else` ghép với `if` gần nhất đủ điều kiện về mặt cú pháp.
- [ ] Xác định được nơi biến cục bộ bắt đầu/kết thúc phạm vi qua dấu ngoặc.
- [ ] Phát hiện được `if (condition);` tạo nhánh rỗng ngoài ý muốn.
- [ ] Biên dịch và chạy được `IndentScopeDemo.java` trên JDK 17+ với các giá trị biên.

**Ghi nhớ:** Thụt lề là **bản đồ dành cho người đọc**, còn ngoặc nhọn `{ }` và quy tắc cú pháp là **cấu trúc mà Java thực sự thực thi**. Khi hai thứ không khớp nhau, máy vẫn chạy theo cú pháp, không theo ý định thể hiện bằng khoảng trắng.
