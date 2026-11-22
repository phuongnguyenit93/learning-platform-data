# Tìm khối `catch` phù hợp gần nhất trong Java

Khi một ngoại lệ được ném, Java cần quyết định **khối `catch` nào sẽ nhận đối tượng ngoại lệ đó**. Quy tắc cốt lõi: Java tìm **trình xử lý phù hợp gần nhất theo luồng thực thi đang hoạt động**, dựa trên kiểu thực tế của ngoại lệ và phạm vi `try/catch` bao quanh vị trí phát sinh lỗi. Nếu không có `catch` phù hợp ở điểm hiện tại, ngoại lệ tiếp tục truyền ra ngoài qua các lời gọi phương thức; trong quá trình đó, các khối `finally` phải chạy theo quy tắc của Java.

Bài học này tập trung vào quá trình tìm `catch` phù hợp và sự thay đổi luồng điều khiển. Đây là một phần của **Java Core – Exception / Luồng thực thi**.

## 1. Thế nào là “`catch` phù hợp”?

Một câu lệnh `catch` có dạng:

~~~java
catch (SomeException e) {
    // Xử lý ngoại lệ.
}
~~~

`catch` phù hợp khi **đối tượng ngoại lệ đang lan truyền có kiểu có thể gán cho kiểu tham số `catch`**. Nói cách khác, kiểu đối tượng có thể là chính kiểu trong `catch` hoặc một lớp con của kiểu đó.

Ví dụ, phân cấp liên quan:

~~~text
Throwable
└── Exception
    └── RuntimeException
        └── IllegalArgumentException
            └── NumberFormatException
~~~

Vì `NumberFormatException` là lớp con của `IllegalArgumentException`, ngoại lệ `new NumberFormatException("sai")` có thể được bắt bằng:

~~~java
catch (NumberFormatException e) { ... }
catch (IllegalArgumentException e) { ... }
catch (RuntimeException e) { ... }
catch (Exception e) { ... }
catch (Throwable e) { ... }
~~~

Những dòng trên là **các lựa chọn minh họa riêng lẻ**, không phải năm `catch` đặt liên tiếp theo thứ tự đó trong cùng một `try`. Trong mã thực tế, các `catch` phải được sắp xếp hợp lệ để nhánh sau không bị nhánh trước che khuất.

Hai điều kiện cần phân biệt:

- **Kiểu tương thích:** `catch (IllegalArgumentException e)` nhận được `NumberFormatException`, nhưng `catch (NullPointerException e)` không nhận được `NumberFormatException` vì không có quan hệ kế thừa tương ứng.
- **Nằm trên đường lan truyền:** `catch` phải thuộc một vùng xử lý bao quanh thao tác ném ngoại lệ trong **chuỗi gọi đang thực thi**. Một `catch` nằm trong phương thức khác nhưng không nằm trên đường gọi hiện tại không có cơ hội nhận lỗi.

Việc so khớp xét **kiểu đối tượng ngoại lệ đang truyền**; thông điệp trong `getMessage()` không quyết định `catch` nào được chạy. Kiểu khai báo của biến tham chiếu cũng không thay thế kiểu runtime của đối tượng khi xác định một `catch` phù hợp.

## 2. Java tìm `catch` theo thứ tự nào?

Hãy xét một ngoại lệ được ném trong phương thức đang thực thi. Có thể theo dõi quá trình bằng các bước sau:

1. **Bắt đầu tại điểm ném ngoại lệ.** Khi `throw` được thực hiện (hoặc API phát sinh ngoại lệ), phần mã bình thường sau điểm đó trong nhánh đang chạy không tiếp tục ngay.
2. **Kiểm tra vùng `try` liên quan gần nhất.** Java xét các nhánh `catch` gắn với `try` đã bao quanh điểm phát sinh ngoại lệ, theo thứ tự khai báo từ trên xuống dưới. Nhánh đầu tiên có kiểu phù hợp sẽ được chọn.
3. **Nếu chưa có nhánh phù hợp, truyền ra phạm vi ngoài.** Các vùng `try` bao quanh khác trong cùng phương thức hoặc ở phương thức gọi có thể có `catch` phù hợp.
4. **Thực thi các khối `finally` liên quan trong quá trình thoát phạm vi.** `finally` thông thường chạy dù tìm thấy `catch` ở tầng ngoài; bản thân `finally` cũng có thể ném ngoại lệ mới và thay đổi kết quả.
5. **Khi gặp `catch` phù hợp, chuyển điều khiển vào khối đó.** Nếu khối xử lý kết thúc bình thường, chương trình tiếp tục sau cấu trúc `try/catch/finally` tương ứng.
6. **Nếu không có trình xử lý phù hợp trên đường gọi**, ngoại lệ thoát khỏi phương thức ngoài cùng của luồng đang thực thi; cơ chế xử lý ngoại lệ chưa bắt của luồng/runtime sẽ tiếp nhận.

Khái niệm “gần nhất” là **gần nhất trong các vùng xử lý đang bao quanh đường thực thi**, có kiểu nhận được ngoại lệ. Nó **không** có nghĩa là dòng `catch` có số dòng nhỏ nhất, phương thức có tên gần nhất, hoặc “bất cứ `catch` nào xuất hiện ở đầu tệp”.

Một `catch` không khớp kiểu không thể “chặn tạm” rồi tự chuyển đổi ngoại lệ thành kiểu đó. Nếu ngoại lệ không phù hợp, Java tiếp tục tìm bên ngoài.

### Sơ đồ luồng tìm handler

~~~text
Một lệnh ném ngoại lệ E
         |
         v
Có catch phù hợp trong vùng try gần nhất?
         | Có
         +------> Vào catch đầu tiên phù hợp
         |
         | Không
         v
Thoát phạm vi hiện tại (thực hiện finally liên quan)
         |
         v
Có vùng try bao ngoài đang hoạt động?
         | Có
         +------> Tìm catch phù hợp tại vùng bao ngoài
         |
         | Không
         v
Ngoại lệ thoát khỏi phương thức / đi về caller
         |
         v
Lặp lại trong các caller đang hoạt động
         |
         v
Không còn handler phù hợp -> ngoại lệ chưa được bắt
~~~

Sơ đồ biểu diễn tư duy theo dõi luồng; trong ngôn ngữ Java, việc hoàn tất các khối `finally`, đóng tài nguyên và xử lý lỗi mới phát sinh có các quy tắc chi tiết hơn trình bày ở phần sau.

## 3. Ví dụ Java 17+ chạy độc lập: tìm `catch` qua nhiều tầng

Tạo tệp **`CatchSearchDemo.java`** với toàn bộ nội dung sau:

~~~java
public class CatchSearchDemo {
    public static void main(String[] args) {
        System.out.println("1) Tim catch qua cac phuong thuc");
        try {
            first();
        } catch (IllegalArgumentException e) {
            System.out.println("main catch: " + e.getMessage());
        } finally {
            System.out.println("main finally");
        }

        System.out.println("2) Catch phu hop trong try gan nhat");
        try {
            try {
                throw new NumberFormatException("abc");
            } catch (IllegalArgumentException e) {
                System.out.println(
                        "inner catch: " + e.getClass().getSimpleName());
            } finally {
                System.out.println("inner finally");
            }
        } catch (IllegalArgumentException e) {
            System.out.println("outer catch");
        }

        System.out.println("3) Catch va nem lai");
        try {
            try {
                throw new IllegalStateException("chua san sang");
            } catch (IllegalStateException e) {
                System.out.println("inner catch: " + e.getMessage());
                throw e;
            } finally {
                System.out.println("inner finally");
            }
        } catch (RuntimeException e) {
            System.out.println(
                    "outer catch: " + e.getClass().getSimpleName());
        }

        System.out.println("4) Catch cu the dung truoc catch cha");
        try {
            Integer.parseInt("7x");
        } catch (NumberFormatException e) {
            System.out.println("specific catch");
        } catch (IllegalArgumentException e) {
            System.out.println("general catch");
        }
    }

    static void first() {
        try {
            middle();
        } catch (NullPointerException e) {
            System.out.println("first null catch");
        } finally {
            System.out.println("first finally");
        }
    }

    static void middle() {
        try {
            leaf();
        } catch (IllegalStateException e) {
            System.out.println("middle state catch");
        } finally {
            System.out.println("middle finally");
        }
    }

    static void leaf() {
        throw new NumberFormatException("bad-number");
    }
}
~~~

Chạy bằng Java 17 hoặc phiên bản mới hơn:

~~~bash
javac CatchSearchDemo.java
java CatchSearchDemo
~~~

Đầu ra chính xác:

~~~text
1) Tim catch qua cac phuong thuc
middle finally
first finally
main catch: bad-number
main finally
2) Catch phu hop trong try gan nhat
inner catch: NumberFormatException
inner finally
3) Catch va nem lai
inner catch: chua san sang
inner finally
outer catch: IllegalStateException
4) Catch cu the dung truoc catch cha
specific catch
~~~

### Diễn giải tình huống 1: đi qua các phương thức

Luồng gọi:

~~~text
main()
  └── first()
        └── middle()
              └── leaf()
                    └── throw NumberFormatException
~~~

Theo dõi lần lượt:

1. `leaf()` ném đối tượng `NumberFormatException("bad-number")`.
2. `middle()` có `catch (IllegalStateException e)`. Ngoại lệ đang truyền **không phải** `IllegalStateException` hoặc lớp con của nó nên không vào nhánh này. Khối `middle finally` được in.
3. `first()` có `catch (NullPointerException e)`. Kiểu không tương thích nên không chạy nhánh `catch`. Khối `first finally` được in.
4. `main()` có `catch (IllegalArgumentException e)`. Vì `NumberFormatException extends IllegalArgumentException`, đây là **handler phù hợp đầu tiên trên đường truyền**. Chương trình in `main catch: bad-number`.
5. `finally` của `main` chạy và in `main finally`. Cấu trúc `try/catch/finally` này kết thúc bình thường, chương trình chuyển sang phần 2.

Điểm đáng chú ý: hai `finally` ở tầng trong chạy **trước** khi `catch` ở `main` bắt ngoại lệ. Các dòng `first null catch` và `middle state catch` **không** được in, vì kiểu của chúng không khớp ngoại lệ.

Quá trình rời các lời gọi do ngoại lệ đang truyền thường được gọi là **stack unwinding**. Các lời gọi bình thường còn nằm trên call stack sẽ được tháo dần cho tới điểm xử lý phù hợp, đồng thời chạy các khối dọn dẹp theo quy tắc của Java.

### Diễn giải tình huống 2: ưu tiên vùng `try` gần hơn

`NumberFormatException` được ném trong `try` bên trong. Vùng đó có `catch (IllegalArgumentException e)`, đủ để nhận vì quan hệ kế thừa. Java vào `inner catch` và tiếp tục chạy `inner finally`. Ngoại lệ đã được xử lý và **không tự động truyền sang `outer catch`**.

“Gần nhất” ở đây được thể hiện bằng quan hệ **bao lồng** giữa hai vùng `try`. Nếu đã có một nhánh `catch` phù hợp trong vùng trong, vùng ngoài không được chạy chỉ vì nó có kiểu cũng tương thích.

### Diễn giải tình huống 3: bắt xong nhưng lại ném tiếp

Khối `inner catch` nhận `IllegalStateException` rồi thực hiện `throw e;`. Đây là **một lần ném tiếp** đối tượng ngoại lệ đang bắt. Sau đó `inner finally` chạy, rồi `catch (RuntimeException e)` ở vùng ngoài nhận ngoại lệ vì `IllegalStateException extends RuntimeException`.

Ngược lại, nếu `inner catch` hoàn tất bình thường và không ném tiếp, `outer catch` sẽ không chạy. Bắt được ngoại lệ **không đồng nghĩa** với việc mọi tầng ngoài đều nhận nó; chỉ những ngoại lệ tiếp tục lan truyền mới được tìm handler tiếp.

### Diễn giải tình huống 4: thứ tự các `catch` cùng một `try`

`Integer.parseInt("7x")` ném `NumberFormatException`. Trong cùng một cấu trúc `try`, `catch (NumberFormatException e)` xuất hiện trước `catch (IllegalArgumentException e)` nên nhánh cụ thể được chọn và chỉ có `specific catch` được in.

Java kiểm tra các nhánh `catch` **theo thứ tự xuất hiện**, dừng ở nhánh phù hợp đầu tiên. Bạn nên đặt loại chuyên biệt trước loại tổng quát.

## 4. Quan hệ kiểu và thứ tự của các nhánh `catch`

Hai đoạn sau **không tương đương**:

Đúng — loại con đứng trước loại cha:

~~~java
try {
    Integer.parseInt("khong-phai-so");
} catch (NumberFormatException e) {
    System.out.println("Sai dinh dang so");
} catch (IllegalArgumentException e) {
    System.out.println("Tham so khong hop le");
}
~~~

Sai — trình biên dịch từ chối vì nhánh sau không thể nhận ngoại lệ mà nhánh trước chưa bắt:

~~~java
try {
    Integer.parseInt("khong-phai-so");
} catch (IllegalArgumentException e) {
    System.out.println("Loi tham so");
} catch (NumberFormatException e) {
    System.out.println("Loi dinh dang so");
}
~~~

Đây là **hai đoạn minh họa**, không phải chương trình độc lập. Trong đoạn sai, `catch (NumberFormatException e)` sẽ bị báo lỗi vì mọi `NumberFormatException` đều đã khớp `IllegalArgumentException` ở phía trên.

| Đối tượng ngoại lệ thực tế | `catch (NumberFormatException)` | `catch (IllegalArgumentException)` | `catch (IOException)` |
| --- | --- | --- | --- |
| `new NumberFormatException()` | Phù hợp | Phù hợp | Không |
| `new IllegalArgumentException()` | Không | Phù hợp | Không |
| `new IOException()` | Không | Không | Phù hợp |

Bảng chỉ xét **khả năng khớp kiểu từng nhánh**; kết quả của toàn bộ cấu trúc phụ thuộc cả thứ tự `catch` và các vùng `try` đang thực sự hoạt động.

### `catch (Exception)` và `catch (Throwable)`

- `catch (Exception e)` nhận các ngoại lệ thuộc nhánh `Exception`, gồm `RuntimeException` và nhiều checked exception, nhưng **không** nhận `Error`.
- `catch (Throwable t)` có thể nhận cả `Exception` và `Error`. Bắt quá rộng có thể nuốt lỗi nghiêm trọng hoặc che giấu lỗi thiết kế. Chỉ nên dùng tại ranh giới được thiết kế rõ chính sách.
- `catch (RuntimeException e)` nhận các lớp con của `RuntimeException`, không nhận những checked exception cùng nhánh `Exception` khác như `IOException`.
- Tính *checked/unchecked* không thay đổi quy tắc tìm `catch` **khi chạy**: trình biên dịch dùng phân loại checked để yêu cầu bắt hoặc khai báo; khi ngoại lệ đã phát sinh, Java tìm handler dựa trên kiểu thực tế và phạm vi.

## 5. `catch` gần nhất không nhất thiết nằm trong cùng phương thức

Xét chuỗi lời gọi:

~~~java
static void controller() {
    try {
        service();
    } catch (IllegalArgumentException e) {
        System.out.println("Du lieu khong hop le");
    }
}

static void service() {
    repository();
}

static void repository() {
    throw new IllegalArgumentException("id sai");
}
~~~

Đây là **đoạn minh họa ba phương thức**. Khi `controller()` đang thực sự gọi `service()` rồi `repository()`, ngoại lệ ném từ `repository()` có thể được `controller()` bắt. Việc hai phương thức trung gian không khai báo `throws IllegalArgumentException` không cản trở lan truyền vì ngoại lệ này là unchecked.

Tuy nhiên, một `catch` trong phương thức `controller()` **không thể** nhận ngoại lệ từ một lần gọi `repository()` thuộc chuỗi gọi hoàn toàn khác. Java không quét toàn bộ mã nguồn để chọn bất kỳ handler nào trông có vẻ phù hợp.

Nếu `service()` đã bắt và xử lý xong ngoại lệ, `controller()` cũng không nhận được chính ngoại lệ đó, trừ khi `service()` ném tiếp ngoại lệ hoặc ném ngoại lệ mới.

### `throws` có định vị handler không?

Không. Khai báo:

~~~java
static void readFile(java.nio.file.Path path)
        throws java.io.IOException {
    java.nio.file.Files.readString(path);
}
~~~

nói rằng ngoại lệ checked có thể thoát khỏi phương thức và người gọi phải đáp ứng quy tắc của trình biên dịch. Nó **không chọn** handler hay thay đổi việc so khớp kiểu tại runtime. Handler thực tế vẫn được quyết định bằng cấu trúc `try/catch` đang hoạt động.

## 6. `catch` bên trong `catch` hoặc `finally` có tự bắt lỗi mới không?

Một chi tiết dễ nhầm: **các nhánh `catch` của một `try` chỉ xử lý ngoại lệ phát sinh từ phần `try` tương ứng**, bao gồm các lời gọi trong phần đó. Khi mã **đã ở trong một khối `catch`**, ngoại lệ mới phát sinh tại chính khối xử lý **không quay lại xét các nhánh `catch` anh em** của cùng `try`.

Ví dụ:

~~~java
try {
    throw new IllegalArgumentException("loi dau");
} catch (IllegalArgumentException e) {
    throw new IllegalStateException("loi trong catch", e);
} catch (IllegalStateException e) {
    System.out.println("Khong bat loi moi o day");
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. `IllegalArgumentException` ban đầu được nhánh thứ nhất bắt. Ngoại lệ `IllegalStateException` mới phát sinh **bên trong nhánh `catch` thứ nhất** sẽ đi ra vùng xử lý bao ngoài, nếu có. Nhánh `catch (IllegalStateException e)` là nhánh anh em nên **không** nhận ngoại lệ mới đó.

Nếu muốn bắt lỗi phát sinh khi xử lý ngoại lệ, hãy tổ chức một vùng `try/catch` bao ngoài hoặc một `try/catch` mới bên trong khối xử lý khi thật sự cần.

Tương tự, ngoại lệ mới phát sinh trong một khối `finally` không được các `catch` gắn với `try` đó xử lý như ngoại lệ từ thân `try`. Nó truyền tới vùng bao ngoài phù hợp.

## 7. Vai trò của `finally` khi tìm handler

Một ngoại lệ có thể đi qua nhiều khối `finally` trước khi được bắt. Thông thường, `finally` chạy khi rời vùng `try/catch` dù rời vì kết thúc bình thường, `return` hay ngoại lệ. Điều này giải thích thứ tự in ở tình huống 1 và 3.

Ví dụ đơn giản:

~~~java
try {
    try {
        throw new IllegalArgumentException("sai");
    } finally {
        System.out.println("don dep ben trong");
    }
} catch (IllegalArgumentException e) {
    System.out.println("bat o ngoai");
}
~~~

Kết quả:

~~~text
don dep ben trong
bat o ngoai
~~~

Đây là **đoạn minh họa** có thể đặt trong `main` để chạy. Khối trong không có `catch`, nhưng `finally` chạy trước khi ngoại lệ được bắt ở ngoài.

**Cảnh báo quan trọng:** Nếu `finally` tự `throw` một ngoại lệ mới, hoặc thực hiện `return` trong lúc ngoại lệ cũ đang truyền, kết quả có thể bị thay đổi: ngoại lệ gốc có thể không còn là ngoại lệ thoát ra. Vì vậy tránh `return` trong `finally` và tránh để công việc dọn dẹp che khuất lỗi chính.

Nếu dùng **try-with-resources**, các tài nguyên được đóng tự động khi ra khỏi `try`. Ngoại lệ phát sinh khi đóng có thể được ghi dưới dạng *suppressed exception* khi thân `try` đã ném lỗi chính; tìm handler cho lỗi chính vẫn theo quy tắc kiểu và phạm vi. Đây là cơ chế khác với việc ném lỗi mới thủ công trong `finally`.

## 8. Khi không tìm thấy `catch` phù hợp

Nếu Java đã đi qua mọi phạm vi xử lý thuộc chuỗi gọi mà không tìm thấy handler phù hợp, ngoại lệ trở thành **uncaught exception** đối với luồng thực thi đó. Thông thường, runtime hiển thị loại ngoại lệ, thông điệp và stack trace qua trình xử lý mặc định của luồng; hành vi cụ thể có thể được framework hoặc `Thread.UncaughtExceptionHandler` điều chỉnh.

Không nên hiểu “không được bắt” là **toàn bộ JVM chắc chắn dừng ngay** trong mọi trường hợp: một luồng nền có thể kết thúc trong khi các luồng khác vẫn hoạt động; framework có thể quản lý lỗi tại ranh giới tác vụ. Với chương trình một luồng đơn giản chạy trong `main`, ngoại lệ không được xử lý thường khiến `main` kết thúc bất thường.

Ví dụ minh họa độc lập nếu đặt trong `main`:

~~~java
throw new IllegalArgumentException("du lieu sai");
~~~

Nếu không có `catch` bao quanh, runtime báo ngoại lệ với stack trace. Không có dòng mã chạy bình thường sau lệnh `throw` trong cùng luồng điều khiển đó.

### Phân biệt ba kết quả sau một lần ném

| Tình huống | Hành vi |
| --- | --- |
| `catch` phù hợp bắt và kết thúc bình thường | Ngoại lệ không tiếp tục truyền; chạy phần còn lại sau cấu trúc theo luồng bình thường |
| `catch` phù hợp bắt rồi `throw e` hoặc ném lỗi mới | Tiếp tục tìm handler ở phạm vi ngoài cho ngoại lệ được ném ra |
| Không tìm được `catch` phù hợp | Ngoại lệ thoát khỏi đường gọi hiện tại và được xử lý như lỗi chưa bắt ở ranh giới luồng/runtime |

## 9. Cách lần theo một lỗi bằng stack trace

Khi thấy stack trace, hãy bắt đầu từ **điểm ném** và **chuỗi lời gọi** để tìm điểm nào đang thực sự bao quanh việc ném ngoại lệ. Chẳng hạn một lỗi được ném trong `leaf()`, đi qua `middle()` và `first()` đến `main()`. Những bước hữu ích:

1. Xác định **kiểu ngoại lệ** thực tế trong dòng đầu, ví dụ `NumberFormatException`.
2. Tìm vị trí phát sinh lỗi trong các frame và xác nhận các phương thức caller đang gọi lẫn nhau.
3. Kiểm tra những vùng `try/catch` thật sự bao quanh các lệnh gọi tương ứng, bắt đầu từ vùng gần nhất.
4. So sánh kiểu của từng `catch` theo quan hệ kế thừa, đồng thời xem thứ tự các nhánh trong cùng một `try`.
5. Xem khối `finally`, đóng tài nguyên hoặc `catch` ném lại để giải thích thứ tự và khả năng thay đổi ngoại lệ.
6. Nếu thấy `Caused by`, phân biệt **ngoại lệ bọc bên ngoài** với **nguyên nhân**. Handler nhận ngoại lệ đang được ném ở tầng đó; Java không tự dò kiểu trong `getCause()` để chọn `catch`.

Ví dụ, `catch (java.io.IOException e)` **không** tự động bắt một `RuntimeException` chỉ vì `runtimeException.getCause()` là `IOException`. Muốn xử lý dựa trên nguyên nhân, tầng phù hợp phải kiểm tra cause một cách chủ động hoặc thiết kế API ném đúng loại ngoại lệ.

Lưu ý: thứ tự frame trong stack trace giúp hiểu chuỗi gọi; nó **không** hiện đầy đủ mọi `try/catch` hay cho biết một `catch` cụ thể có đang nằm trong phạm vi xử lý hay không. Để kết luận chắc chắn, cần đối chiếu mã nguồn và luồng điều khiển thực tế.

## 10. Những lỗi hiểu sai phổ biến

**Sai lầm 1 — “Java tìm `catch` khớp tên ngoại lệ gần nhất trong tệp.”**

Java tìm theo **phạm vi thực thi**, không theo thứ tự văn bản toàn cục. Một nhánh `catch` trong phương thức chưa được gọi không liên quan.

**Sai lầm 2 — “`catch` cùng lớp gần nhất luôn được ưu tiên dù nó ở ngoài `try` bên trong.”**

Nếu `try` bên trong đã có một nhánh kiểu cha nhận được ngoại lệ, nó xử lý trước vùng ngoài. Java không bỏ qua handler gần để tìm một handler chuyên biệt hơn ở xa.

**Sai lầm 3 — “Các nhánh `catch` được thử hết rồi tất cả nhánh khớp đều chạy.”**

Trong **một `try`**, chỉ nhánh đầu tiên khớp được chọn. Sau khi nhánh đó xử lý xong bình thường, các nhánh còn lại không chạy.

**Sai lầm 4 — “Nhánh `catch` kiểu cha đứng trước kiểu con cũng được.”**

Nếu kiểu cha đã bao trùm hoàn toàn kiểu con, nhánh kiểu con ở sau là không thể tới; Java báo lỗi biên dịch.

**Sai lầm 5 — “`finally` chỉ chạy khi có `catch` nhận ngoại lệ.”**

`finally` thông thường chạy cả khi không có `catch` phù hợp và trong quá trình ngoại lệ đang truyền ra tầng ngoài. Những trường hợp kết thúc tiến trình hoặc VM bất thường có thể ngăn bảo đảm này; không dựa vào `finally` cho tình huống JVM bị chấm dứt đột ngột.

**Sai lầm 6 — “Một `catch` tiếp theo trong cùng cấu trúc sẽ nhận lỗi do `catch` trước ném.”**

Không. Lỗi từ mã xử lý `catch` phải tìm handler thuộc phạm vi bao ngoài hoặc một `try` khác.

**Sai lầm 7 — “Chỉ checked exception mới lan qua phương thức.”**

Cả checked và unchecked đều có thể truyền qua nhiều phương thức. Checked khác ở nghĩa vụ bắt/khai báo lúc biên dịch; tìm `catch` lúc chạy vẫn theo kiểu và phạm vi.

**Sai lầm 8 — “Bắt `Exception` là bắt mọi thứ có thể ném.”**

`Error` là nhánh khác của `Throwable` nên không được `catch (Exception e)` nhận. Tránh bắt `Throwable` một cách đại trà chỉ để cố gắng tiếp tục sau lỗi nghiêm trọng.

## 11. Bài tập tự kiểm tra

**Câu 1.** `NumberFormatException` được ném trong một `try` có `catch (IllegalArgumentException e)`. `catch` này có khớp không? Vì sao?

**Câu 2.** Phương thức `a()` gọi `b()`, `b()` gọi `c()`. `c()` ném `IllegalStateException`; `b()` chỉ có `catch (NullPointerException e)`; `a()` có `catch (RuntimeException e)`. `catch` nào được chọn?

**Câu 3.** Nếu cả vùng `try` bên trong và vùng `try` bên ngoài đều có `catch (Exception e)`, và ngoại lệ phát sinh trong vùng bên trong, vùng nào nhận trước?

**Câu 4.** Nếu `catch` bên trong nhận được ngoại lệ nhưng thực hiện `throw e;`, điều gì xảy ra tiếp theo? `finally` có thể chạy ở thời điểm nào?

**Câu 5.** Vì sao không thể đặt `catch (RuntimeException e)` trước `catch (NumberFormatException e)` trong cùng một cấu trúc `try`?

**Câu 6.** Một phương thức ném `new IllegalStateException("x", new IOException("root"))`. Nếu `catch` ngoài chỉ bắt `IOException`, nó có nhận ngoại lệ đang lan truyền không? Vì sao?

**Câu 7.** Khi không có `catch` phù hợp ở `main`, chắc chắn mọi luồng khác trong JVM đều phải dừng ngay hay không?

### Đáp án gợi ý

1. Có, vì `NumberFormatException` là lớp con của `IllegalArgumentException`.
2. `catch (RuntimeException e)` của `a()`; nhánh trong `b()` không khớp kiểu.
3. Vùng trong nhận trước nếu ngoại lệ phát sinh trong `try` của nó và nhánh đó phù hợp.
4. Ngoại lệ tiếp tục truyền ra vùng ngoài; `finally` liên quan thường chạy khi thoát khối trước khi handler ngoài nhận.
5. Vì nhánh `RuntimeException` đã nhận mọi `NumberFormatException`, khiến nhánh sau không thể đạt tới.
6. Không. Đối tượng đang truyền là `IllegalStateException`; `IOException` chỉ là nguyên nhân lưu ở `cause`.
7. Không. Ngoại lệ chưa bắt làm ảnh hưởng tới luồng đó; hệ quả toàn tiến trình phụ thuộc các luồng và môi trường quản lý tác vụ.

## 12. Ghi nhớ quy tắc cốt lõi

Khi Java gặp ngoại lệ, hãy hỏi **“vùng xử lý nào đang bao quanh điểm ném và có `catch` nhận được kiểu đối tượng đó?”**. Java ưu tiên vùng gần nhất đang hoạt động; trong cùng một vùng, ưu tiên nhánh `catch` phù hợp đầu tiên. Nếu không có, ngoại lệ truyền qua các tầng gọi, thực hiện dọn dẹp liên quan, cho đến khi gặp handler phù hợp hoặc trở thành ngoại lệ chưa bắt. Hiểu được đường truyền này giúp bạn dự đoán stdout, tìm đúng điểm lỗi và chọn vị trí xử lý ngoại lệ mà không bắt lỗi quá rộng.