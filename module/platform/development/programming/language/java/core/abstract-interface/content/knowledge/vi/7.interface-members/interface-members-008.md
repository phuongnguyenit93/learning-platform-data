# Giới hạn tham chiếu field và thứ tự khai báo trong interface Java

## 1. Hai vấn đề cần phân biệt

Trong initializer của field interface, Java hạn chế tham chiếu bằng **tên đơn** đến chính field đó hoặc field được khai báo phía sau. Đây là quy tắc lúc biên dịch. Một trường hợp khác là tham chiếu qualified name hợp lệ về cú pháp nhưng đọc field runtime trước khi nó được gán; khi đó kết quả có thể là giá trị mặc định.

Field interface luôn là public static final và phải có initializer. Để phân biệt constant variable với field được tính lúc runtime, xem bài về hằng thời điểm biên dịch.

## 2. Simple-name forward reference và tự tham chiếu

Ví dụ sau không biên dịch:

~~~java
interface BadOrder {
    int FIRST = SECOND + 1;
    int SECOND = 5;
}
~~~

SECOND được dùng bằng tên đơn trong initializer của FIRST trước vị trí khai báo SECOND. Việc SECOND là hằng biên dịch không làm hợp lệ tham chiếu này.

Tự tham chiếu trực tiếp cũng sai:

~~~java
interface BadSelfReference {
    int COUNT = COUNT + 1;
}
~~~

Các declarator trên cùng dòng cũng tuân theo thứ tự từ trái sang phải:

~~~java
interface ValidOrder {
    int BASE = 5, NEXT = BASE + 1;
}
~~~

BASE đã được khai báo trước NEXT nên biểu thức NEXT hợp lệ. Quy tắc này nhắm vào initializer của field; thân phương thức có thể dùng field khai báo ở phía sau.

## 3. Qualified name có thể hợp lệ nhưng nguy hiểm lúc chạy

Tên đủ nghĩa như RuntimeOrder.LATER tránh lỗi simple-name forward reference. Tuy nhiên, nó không tự sắp xếp việc khởi tạo runtime.

~~~java
interface RuntimeOrder {
    int EARLY = RuntimeOrder.LATER;
    int LATER = supply();

    static int supply() {
        return 42;
    }
}
~~~

Khi khởi tạo interface, EARLY được gán trước khi initializer của LATER chạy. Lúc đó LATER còn có giá trị mặc định 0, nên EARLY nhận 0; sau đó LATER nhận 42.

Trái lại, nếu field phía sau là constant variable, giá trị hằng có thể được biết ngay lúc biên dịch:

~~~java
interface QualifiedConstant {
    int FIRST = QualifiedConstant.SECOND;
    int SECOND = 7;
}
~~~

FIRST nhận 7. Hai trường hợp có cú pháp gần giống nhau nhưng hành vi khác nhau vì một field là constant variable, field kia cần initializer runtime.

## 4. Ví dụ Java 17+ hoàn chỉnh

Lưu vào **Main.java**:

~~~java
interface RuntimeOrder {
    int EARLY = RuntimeOrder.LATER;
    int LATER = supply();

    static int supply() {
        return 42;
    }
}

interface QualifiedConstant {
    int FIRST = QualifiedConstant.SECOND;
    int SECOND = 7;
}

public class Main {
    public static void main(String[] args) {
        System.out.println(RuntimeOrder.EARLY);
        System.out.println(RuntimeOrder.LATER);
        System.out.println(QualifiedConstant.FIRST);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả:

~~~text
0
42
7
~~~

Lúc khởi tạo RuntimeOrder, static fields được chuẩn bị với giá trị mặc định rồi các initializer được thực hiện theo thứ tự khai báo. EARLY đọc LATER trước khi lời gọi supply gán giá trị 42. QualifiedConstant.SECOND là constant variable nên FIRST nhận 7.

## 5. Method call, field kế thừa và tên trùng nhau

Lời gọi phương thức trong initializer không phải tham chiếu field bằng tên đơn, vì vậy cú pháp này hợp lệ:

~~~java
interface Computed {
    int PORT = defaultPort();

    static int defaultPort() {
        return 8080;
    }
}
~~~

PORT không phải constant variable vì initializer gọi phương thức. Tuy nhiên, nếu phương thức được gọi gián tiếp đọc field runtime chưa được gán, thứ tự khởi tạo vẫn có thể tạo giá trị bất ngờ.

Field được kế thừa từ interface cha cũng có thể được sử dụng trong initializer của interface con:

~~~java
interface ParentLimits {
    int MAX = 20;
}

interface ChildLimits extends ParentLimits {
    int WARNING = MAX - 5;
}
~~~

Nếu hai interface cha độc lập cùng khai báo TIMEOUT, tên đơn TIMEOUT có thể mơ hồ. Đây là lỗi phân giải tên, khác với forward reference do vị trí khai báo. Dùng East.TIMEOUT hoặc West.TIMEOUT theo đúng ý nghĩa cần lấy.

## 6. Cách tổ chức khai báo an toàn

- Khai báo field nền trước field phụ thuộc.
- Với field runtime, tránh phụ thuộc ngược hoặc vòng giữa các initializer.
- Khi compiler báo illegal forward reference, kiểm tra xem initializer dùng simple name của field khai báo phía sau hay tự tham chiếu.
- Đừng thêm tên interface vào trước field chỉ để làm compiler hết báo lỗi mà không xem xét thứ tự runtime.
- Chuyển cấu hình phức tạp hoặc có side effect sang factory/service nếu thời điểm khởi tạo cần được kiểm soát.
- Khi nhiều interface cha có tên field giống nhau, dùng qualifier của interface định nghĩa field cần đọc.

### Tự kiểm tra

1. FIRST dùng SECOND bằng tên đơn khi SECOND khai báo phía sau: **lỗi biên dịch**.
2. FIRST dùng QualifiedConstant.SECOND, với SECOND = 7: **hợp lệ và nhận 7**.
3. EARLY dùng RuntimeOrder.LATER, với LATER = supply(): **EARLY có thể nhận 0** vì initializer runtime của LATER chưa chạy.
4. Một static method có thể được khai báo sau field gọi nó không? **Có**, nhưng cần xem nó phụ thuộc field runtime nào.

Đọc theo ba câu hỏi: tên tham chiếu là simple name hay qualified name; field đích đã được khai báo trước chưa; và giá trị là constant variable hay chỉ được tính khi interface khởi tạo.