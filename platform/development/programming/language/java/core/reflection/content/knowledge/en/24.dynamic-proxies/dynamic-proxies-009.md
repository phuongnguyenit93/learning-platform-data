# Checked exception và UndeclaredThrowableException trong Java Dynamic Proxy

## 1. Bối cảnh và mục tiêu

Trong JDK Dynamic Proxy, lời gọi một phương thức của interface được chuyển tới **InvocationHandler.invoke(proxy, method, args)**. Handler có thể gọi một đối tượng đích, trả kết quả hoặc ném ngoại lệ. Vấn đề là **InvocationHandler.invoke** khai báo **throws Throwable**, nhưng phương thức trên interface được proxy triển khai vẫn có hợp đồng checked exception riêng.

Ví dụ, nếu interface khai báo **String read() throws IOException**, caller được chuẩn bị để xử lý **IOException**. Khi handler ném một **SQLException** không nằm trong hợp đồng, lớp proxy do JDK tạo ra không chuyển ngoại lệ checked này nguyên trạng: nó bọc bằng **UndeclaredThrowableException** (UTE), một unchecked exception.

Mục tiêu bài học là:
- Hiểu ranh giới giữa **throws** của phương thức interface và **throws Throwable** của invocation handler.
- Dự đoán khi nào ngoại lệ đi qua trực tiếp, khi nào được bọc bởi **UndeclaredThrowableException**.
- Phân biệt wrapper proxy với **InvocationTargetException** do **Method.invoke** tạo khi target ném lỗi.
- Viết handler ủy quyền có thể chuyển tiếp hoặc chuyển đổi ngoại lệ đúng hợp đồng, đồng thời giữ nguyên nguyên nhân gốc.

**Kiến thức cần trước:** checked/unchecked exception, **throw**, **throws**, interface, **Proxy.newProxyInstance**, **InvocationHandler**, **Method.invoke**.

## 2. Ba nhóm ngoại lệ cần phân biệt

**Checked exception** gồm các lớp con của **Exception** ngoại trừ **RuntimeException** và những lớp con của nó. Ví dụ **IOException**, **SQLException**, **ClassNotFoundException**. Với lời gọi được kiểm tra tĩnh, Java yêu cầu caller bắt hoặc khai báo chúng.

**Unchecked exception** là **RuntimeException** và các lớp con, hoặc **Error** và các lớp con. Ví dụ **IllegalArgumentException**, **IllegalStateException**, **AssertionError**. Những ngoại lệ này không cần xuất hiện trong mệnh đề **throws**.

**Ngoại lệ được phép bởi hợp đồng interface** là checked exception có kiểu tương thích với ít nhất một kiểu được phương thức khai báo trong **throws**. Ví dụ:

~~~java
interface Reader {
    String read() throws java.io.IOException;
}
~~~

Một **FileNotFoundException** là lớp con của **IOException**, nên được phép đi qua lời gọi **Reader.read()**. **SQLException** không tương thích với **IOException** và không được phép đi qua như một checked exception nguyên trạng.

Điều cần nhớ: **InvocationHandler.invoke** nhận trách nhiệm xử lý động ở runtime, còn **Reader.read()** là hợp đồng Java mà caller nhìn thấy. Trình biên dịch không thể biết handler nào sẽ được gắn vào proxy trong lúc chạy, nên JDK tạo lớp proxy bảo đảm quy tắc truyền ngoại lệ của interface.

## 3. Chính xác khi nào JDK Proxy ném UndeclaredThrowableException?

Khi **InvocationHandler.invoke** kết thúc bằng cách ném ngoại lệ, phương thức trên proxy xử lý về mặt ý nghĩa như sau:

| Throwable rời handler | Hợp đồng **read() throws IOException** | Kết quả |
| --- | --- | --- |
| **IOException("disk")** | Tương thích **IOException** | Caller nhận **IOException** trực tiếp |
| **FileNotFoundException("missing")** | Là lớp con của **IOException** | Caller nhận **FileNotFoundException** trực tiếp |
| **SQLException("db")** | Không tương thích **IOException** | Proxy ném **UndeclaredThrowableException** chứa **SQLException** |
| **IllegalStateException("bad")** | Unchecked | Caller nhận **IllegalStateException** trực tiếp |
| **AssertionError("bad")** | **Error**, unchecked | Caller nhận **AssertionError** trực tiếp |
| **InvocationTargetException** chứa **IOException** | Kiểu của wrapper không tương thích **IOException** | Proxy ném **UndeclaredThrowableException** chứa **InvocationTargetException** |

Luồng gọi:

~~~text
Caller -> proxy.read() -> InvocationHandler.invoke(...)
                          |
                          +-- trả giá trị ----------------> Caller
                          +-- RuntimeException / Error ---> Ném trực tiếp
                          +-- checked được khai báo ------> Ném trực tiếp
                          +-- checked ngoài hợp đồng -----> UndeclaredThrowableException
                                                            -> Caller
~~~

**UndeclaredThrowableException** thuộc gói **java.lang.reflect**, kế thừa **RuntimeException**, vì vậy caller không bị compiler buộc phải bắt nó. API **getUndeclaredThrowable()** trả về đúng Throwable mà proxy đã bọc; **getCause()** cung cấp nguyên nhân tương ứng.

Khi phương thức interface **không có throws**, mọi checked exception rời handler đều bị bọc theo quy tắc này. Ngược lại, interface khai báo **throws Exception** có thể cho nhiều checked exception đi qua, nhưng không có nghĩa nên khai báo như vậy: cần thiết kế hợp đồng có ý nghĩa cho caller.

## 4. Ví dụ đầy đủ Java 17+: bốn tình huống khác nhau

Lưu chương trình sau trong tệp **ProxyExceptionDemo.java**. Interface **Reader.read()** khai báo **IOException**. Target thật luôn ném **IOException("disk")**. Handler có bốn nhánh để thấy chính xác ngoại lệ nào rời khỏi proxy.

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.sql.SQLException;

public class ProxyExceptionDemo {
    public interface Reader {
        String read() throws IOException;
    }

    public static class FailingReader implements Reader {
        @Override
        public String read() throws IOException {
            throw new IOException("disk");
        }
    }

    enum Mode {
        DIRECT_CHECKED, UNDECLARED, BAD_DELEGATION, GOOD_DELEGATION
    }

    static void run(Mode mode) {
        Reader reader = (Reader) Proxy.newProxyInstance(
                ProxyExceptionDemo.class.getClassLoader(),
                new Class<?>[]{Reader.class},
                (proxy, method, args) -> {
                    if (mode == Mode.DIRECT_CHECKED) {
                        throw new IOException("disk");
                    }
                    if (mode == Mode.UNDECLARED) {
                        throw new SQLException("db");
                    }
                    if (mode == Mode.BAD_DELEGATION) {
                        // Method.invoke bọc lỗi target trong
                        // InvocationTargetException: đây là
                        // một checked exception chưa được tháo.
                        return method.invoke(new FailingReader(), args);
                    }

                    // GOOD_DELEGATION: truyền lại lỗi thật của target.
                    try {
                        return method.invoke(new FailingReader(), args);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });

        try {
            reader.read();
        } catch (IOException e) {
            System.out.println(
                    mode + ": IOException(" + e.getMessage() + ")");
        } catch (UndeclaredThrowableException e) {
            Throwable cause = e.getUndeclaredThrowable();
            if (cause instanceof InvocationTargetException ite) {
                cause = ite.getCause();
            }
            System.out.println(mode + ": UTE("
                    + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage() + ")");
        }
    }

    public static void main(String[] args) {
        for (Mode mode : Mode.values()) {
            run(mode);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ProxyExceptionDemo.java
java ProxyExceptionDemo
~~~

Đầu ra:

~~~text
DIRECT_CHECKED: IOException(disk)
UNDECLARED: UTE(SQLException:db)
BAD_DELEGATION: UTE(IOException:disk)
GOOD_DELEGATION: IOException(disk)
~~~

**Giải thích chi tiết:**

1. **DIRECT_CHECKED:** handler trực tiếp ném **IOException**. Vì **Reader.read()** có **throws IOException**, proxy chuyển ngoại lệ đúng kiểu ra ngoài; **catch (IOException)** nhận được.
2. **UNDECLARED:** handler ném **SQLException**, không tương thích với hợp đồng **throws IOException**. Proxy tạo **UndeclaredThrowableException**, đối tượng **SQLException** nằm trong **getUndeclaredThrowable()**.
3. **BAD_DELEGATION:** target ném **IOException**, nhưng **Method.invoke** bắt ngoại lệ target và ném **InvocationTargetException**. Handler không tháo wrapper, nên Throwable rời handler chính là **InvocationTargetException**, vốn không thuộc **throws IOException**. Proxy bọc thêm một tầng UTE.
4. **GOOD_DELEGATION:** handler bắt **InvocationTargetException** và ném **getCause()**. Throwable rời handler là **IOException** của target; proxy chuyển nguyên trạng để caller bắt bằng **catch (IOException)**.

Kết quả trên đã được đối chiếu qua chạy thử Java; thứ tự hiển thị chính là thứ tự các giá trị trong enum **Mode**. Ví dụ dùng import tường minh cho **java.lang.reflect.Proxy** và chương trình có thể biên dịch độc lập bằng JDK 17+.

## 5. InvocationTargetException khác gì UndeclaredThrowableException?

| Câu hỏi | **InvocationTargetException** | **UndeclaredThrowableException** |
| --- | --- | --- |
| Ai tạo wrapper? | **Method.invoke** khi code của method được gọi ném Throwable | Mã phương thức proxy do JDK tạo khi handler ném checked exception ngoài hợp đồng |
| Là checked hay unchecked? | Checked, kế thừa **ReflectiveOperationException** | Unchecked, kế thừa **RuntimeException** |
| Wrapper chứa gì? | Ngoại lệ thật do target ném | Throwable mà invocation handler đã ném ra nhưng interface không khai báo hợp lệ |
| Lấy nguyên nhân | **getCause()** hoặc **getTargetException()** | **getUndeclaredThrowable()** hoặc **getCause()** |
| Sửa ở đâu? | Bắt và tháo wrapper ngay tại handler khi ủy quyền bằng Reflection | Sửa hợp đồng hoặc cách handler phát sinh/chuyển đổi checked exception |

Một chuỗi điển hình của nhánh **BAD_DELEGATION**:

~~~text
UndeclaredThrowableException
  -> InvocationTargetException
       -> IOException("disk")
~~~

Không nên chỉ đọc dòng exception ngoài cùng rồi kết luận đối tượng đích ném sai kiểu. Target có thể ném **IOException** hoàn toàn phù hợp; lỗi nằm ở việc handler để **InvocationTargetException** vượt qua ranh giới proxy.

Nếu target ném **IllegalArgumentException** qua **Method.invoke**, Reflection vẫn bọc lỗi trong **InvocationTargetException**. Handler không tháo wrapper có thể khiến caller nhận UTE dù bản thân **IllegalArgumentException** là unchecked và đáng lẽ có thể được ném trực tiếp.

## 6. Mẫu handler chuyển tiếp ngoại lệ đúng cách

Khi handler chỉ ủy quyền từ proxy sang đối tượng thật bằng **Method.invoke**, mẫu cơ bản là:

~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException e) {
    throw e.getCause();
}
~~~

Đây là **đoạn trích dùng bên trong InvocationHandler.invoke**, giả sử biến **target** tồn tại và **method/args** là tham số callback. Nó không phải một chương trình độc lập. **InvocationHandler.invoke** khai báo **throws Throwable** nên có thể ném **e.getCause()**.

Tuy nhiên, **tháo InvocationTargetException chưa bảo đảm mọi checked exception đều hợp lệ**. Nếu target ném một **SQLException** trong khi interface chỉ khai báo **IOException**, proxy vẫn bọc SQLException bằng UTE. Cần xác định chính sách lỗi:

- **Chuyển tiếp nguyên nhân thật** nếu nó tương thích với hợp đồng **throws** của interface. Không cần đổi kiểu.
- **Chuyển đổi có ý nghĩa** nếu ngoại lệ của thư viện/hạ tầng không thuộc hợp đồng API. Ví dụ, một lỗi đọc tài liệu từ cơ sở dữ liệu có thể chuyển thành **IOException** nhưng cần kèm cause.
- **Giữ nguyên nguyên nhân** trong exception mới. Không nuốt exception hay ném wrapper không có cause làm mất dữ kiện chẩn đoán.
- **Sửa thiết kế hợp đồng** nếu caller thật sự phải xử lý một checked exception bổ sung; không mở rộng bừa bãi thành **throws Throwable** để né quy tắc.

Ví dụ minh họa chuyển một lỗi từ tầng dữ liệu thành lỗi đọc tài liệu:

~~~java
try {
    return loadDocumentFromDatabase();
} catch (java.sql.SQLException e) {
    throw new java.io.IOException("Không thể đọc tài liệu", e);
}
~~~

Đoạn này giả định có phương thức **loadDocumentFromDatabase()** có thể ném **SQLException** và code nằm trong handler cho phương thức interface **throws IOException**. Trình biên dịch sẽ cần triển khai đầy đủ phương thức đó nếu đưa ví dụ vào dự án. Không dùng chuyển đổi này tùy tiện khi không có quan hệ ý nghĩa giữa lỗi dữ liệu và lỗi đọc.

## 7. Các trường hợp biên

### 7.1. Không khai báo checked exception

Với interface có phương thức **void execute()** và không khai báo **throws**, handler ném **IOException** sẽ dẫn đến UTE. **throws Throwable** trên handler không thay đổi chữ ký của **execute()**.

### 7.2. Một proxy triển khai nhiều interface trùng chữ ký

Nếu các interface cùng khai báo một phương thức có cùng tên và cùng danh sách tham số nhưng **throws** khác nhau, checked exception đi ra từ handler phải tương thích với hợp đồng của **tất cả** những interface mà lời gọi tương ứng có thể thực hiện. Không đủ để exception chỉ tương thích với một interface.

Ví dụ **A.process() throws IOException** và **B.process() throws SQLException**: khi proxy triển khai cả **A** lẫn **B**, handler ném **IOException** sẽ bị proxy bọc trong UTE vì kiểu đó không tương thích với **throws SQLException** của **B.process()**. Đây là đặc điểm của các phương thức trùng chữ ký, không phụ thuộc cách caller ép kiểu proxy sang **A** hay **B**.

### 7.3. Các phương thức equals, hashCode và toString

Lời gọi **equals**, **hashCode**, **toString** trên proxy cũng được chuyển qua handler. Chúng không khai báo checked exception, nên handler ném checked exception cho các lời gọi này cũng tạo UTE. Cần quyết định rõ cách xử lý ba method đó trong handler nếu ứng dụng dùng chúng.

### 7.4. IllegalAccessException khi gọi Reflection

Nếu **Method.invoke** ném **IllegalAccessException** do quyền truy cập, đây là checked exception ở tầng Reflection, không phải lỗi được target ném và được bọc trong **InvocationTargetException**. Nếu handler chuyển nguyên nó ra ngoài nhưng interface không khai báo loại tương thích, proxy bọc UTE. Cách khắc phục cần xem quyền truy cập và module Java thực tế; tháo wrapper hoặc gọi **setAccessible(true)** tùy tiện không tự giải quyết mọi trường hợp.

## 8. Hướng chẩn đoán khi gặp UTE

1. **Kiểm tra mệnh đề throws trên interface.** Ghi lại phương thức được caller gọi và các interface có phương thức trùng chữ ký.
2. **Lấy throwable nằm trong UTE.** Gọi **getUndeclaredThrowable()** (hoặc **getCause()**). Đừng chỉ dựa vào tên UTE.
3. **Kiểm tra có InvocationTargetException không.** Nếu có, đọc tiếp **getCause()** để biết lỗi thật của target.
4. **Tìm đúng đoạn code trong handler.** Đoạn nào ném Throwable ra khỏi **InvocationHandler.invoke**? Đây là loại checked hợp lệ, loại ngoài hợp đồng, hay wrapper Reflection bị quên?
5. **Sửa đúng ranh giới.** Nếu target ném lỗi đã được khai báo nhưng handler để lọt wrapper, tháo wrapper. Nếu target thực sự ném checked exception ngoài hợp đồng, thiết kế lại cách chuyển đổi hoặc chữ ký interface.
6. **Kiểm thử cả hai đường gọi.** Gọi target trực tiếp để ghi nhận nguyên nhân, rồi gọi qua proxy để xác nhận kiểu exception caller thấy.

Có thể ghi lại chuỗi cause đầy đủ tại điểm giám sát, nhưng không nên luôn bắt UTE ở tất cả caller như biện pháp thay cho việc sửa handler.

## 9. Lỗi phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Cho rằng **throws Throwable** của handler cho phép mọi checked exception tới caller | UTE xuất hiện ở runtime | Đối chiếu ngoại lệ với **throws** của interface |
| Ủy quyền bằng **return method.invoke(target, args)** mà không bắt **InvocationTargetException** | UTE có thể chứa **InvocationTargetException** dù lỗi gốc hợp lệ | Bắt wrapper và **throw e.getCause()** |
| Chuyển mọi exception sang **new RuntimeException()** không truyền cause | Mất thông tin gốc, khó xác định lỗi | Giữ cause và chọn exception đúng ngữ nghĩa |
| Ép kiểu mọi cause thành **IOException** | Có thể gây lỗi ép kiểu và che bug | Kiểm tra loại và chuyển đổi có chủ đích |
| Caller chỉ bắt checked exception đã khai báo và cho rằng đã xử lý mọi lỗi | UTE unchecked vẫn thoát ra | Sửa handler và theo dõi UTE ở ranh giới thích hợp |
| Chỉ nhìn thông báo UTE thay vì chuỗi cause | Chẩn đoán nhầm nguồn lỗi | Dùng **getUndeclaredThrowable()** và **getCause()** |

## 10. Thực hành và tự kiểm tra

**Bài tập 1:** Đổi interface thành phương thức **read()** không khai báo **IOException** nhưng giữ handler ném **IOException**. Sau khi chỉnh implementation để chương trình biên dịch, dự đoán kết quả: caller nhận **UndeclaredThrowableException**, bên trong là **IOException**.

**Bài tập 2:** Cho target ném **IllegalArgumentException**. So sánh handler chỉ gọi **Method.invoke** với handler bắt **InvocationTargetException** rồi ném **getCause()**. Trường hợp đầu tạo UTE chứa wrapper; trường hợp sau cho **IllegalArgumentException** thoát ra trực tiếp.

**Bài tập 3:** Cho handler ném **SQLException** khi interface chỉ khai báo **IOException**. Viết cách chuyển đổi sang **IOException** có cause, sau đó xác minh caller bắt **IOException** và đọc được **SQLException** từ **getCause()**.

**Bài tập 4:** Tạo hai interface cùng khai báo **process()** nhưng một bên **throws IOException**, bên kia **throws SQLException**. Tạo proxy triển khai cả hai và giải thích vì sao việc ném **IOException** trực tiếp từ handler dẫn đến UTE.

**Câu hỏi tự kiểm tra:**
- Vì sao **InvocationHandler.invoke throws Throwable** không xóa bỏ giới hạn checked exception của interface?
- Khi UTE chứa **InvocationTargetException** chứa **IOException**, ngoại lệ nào thực sự rời khỏi handler?
- Khi target ném **RuntimeException** qua **Method.invoke**, có cần tháo **InvocationTargetException** không?
- Vì sao sửa lỗi UTE bằng cách luôn thêm **throws Exception** vào interface có thể làm giảm chất lượng hợp đồng API?

**Đáp án cốt lõi:** Proxy bảo toàn hợp đồng của interface; **InvocationTargetException** là wrapper checked do Reflection tạo; nên tháo wrapper để truyền nguyên nhân thật; việc mở rộng **throws** phải phục vụ cách caller xử lý lỗi, không được dùng như mẹo che lỗi thiết kế.

Khi đã trả lời được các câu hỏi trên và dự đoán đúng cả bốn dòng output, bạn đã hiểu được mối liên hệ giữa checked exception, cơ chế ủy quyền Reflection và **UndeclaredThrowableException** của JDK Dynamic Proxy.
