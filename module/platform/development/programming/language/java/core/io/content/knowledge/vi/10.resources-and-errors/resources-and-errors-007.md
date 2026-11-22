# Cleanup khi tạo hoặc ghép tài nguyên thất bại trong Java I/O

## 1. Vấn đề: đã mở một phần nhưng chưa xây dựng xong

Trong Java I/O, tài nguyên có thể là file, socket, stream, reader, writer, temporary file, channel hay một đối tượng quản lý nhiều tài nguyên. Chúng thường giữ file descriptor/handle hoặc bộ đệm cần được đóng. Nếu mã nguồn mở nhiều tài nguyên hoặc ghép các wrapper mà **bước sau ném exception**, những tài nguyên mở thành công trước đó vẫn cần được dọn dẹp.

Ví dụ luồng công việc:

~~~text
mở file A           [thành công]
mở file B           [thất bại]
xử lý A và B        [chưa chạy]
cleanup file A      [bắt buộc]
báo lỗi mở B        [giữ nguyên nguyên nhân]
~~~

Nếu không cleanup file A, ứng dụng có thể rò rỉ descriptor, giữ khóa file hoặc không giải phóng kết nối dù phương thức chưa trả về đối tượng kết quả. Đây là **partial initialization / partial acquisition**: một số tài nguyên đã được cấp phát, nhưng thao tác tạo tổng thể chưa thành công.

Vấn đề có hai trường hợp phải phân biệt:

1. **Tài nguyên A đã được tạo thành công, rồi lúc mở tài nguyên B có lỗi:** try-with-resources (TWR) có thể tự đóng A.
2. **Constructor/factory của chính B đã mở tài nguyên nội bộ rồi mới lỗi:** B chưa được tạo thành công nên bên gọi chưa có tham chiếu B để đóng. Constructor/factory phải tự cleanup phần tài nguyên nội bộ đã mở.

Một lỗi nữa có thể xảy ra **ngay trong cleanup**: phương thức close() có thể ném IOException hoặc exception khác. Code đúng phải bảo toàn lỗi gốc và tránh che khuất nó bằng lỗi đóng tài nguyên.

## 2. Hợp đồng sở hữu tài nguyên (ownership)

Để cleanup nhất quán, mỗi API cần có quy định rõ:

- **Ai mở thì ai có trách nhiệm đóng**, trừ khi giao quyền sở hữu qua hợp đồng đã xác định.
- Một phương thức **trả về thành công** một stream/wrapper có thể chuyển trách nhiệm đóng cho bên gọi.
- Một phương thức **thất bại trước khi trả về** phải dọn các tài nguyên nó đang sở hữu, kể cả những tài nguyên đã mở thành công một phần.
- Khi wrapper nhận ownership của stream bên dưới, **đóng wrapper thường sẽ đóng stream nền**. Nếu vừa đóng wrapper vừa đóng riêng stream nền, tài nguyên có thể bị close nhiều lần.
- Đừng ngầm giả định close luôn không lỗi hay luôn idempotent. Cần xem hợp đồng cụ thể của tài nguyên.

Ví dụ khi gọi **new BufferedInputStream(raw)**, wrapper sẽ sử dụng raw; lúc close wrapper, nó đóng raw theo hợp đồng lớp. Với một decorator do ứng dụng tự xây dựng, hợp đồng phải nói rõ wrapper **sở hữu** hay chỉ **mượn** stream. Tránh cả hai thái cực: không ai đóng gây leak, hoặc nhiều bên cùng đóng dẫn tới double-close và lỗi trạng thái.

**Giữ tài nguyên sống** không tương đương **giữ reference Java**: garbage collector có thể thu gom đối tượng, nhưng không nên dựa vào GC hoặc finalizer để giải phóng tài nguyên I/O đúng thời điểm. Dùng try-with-resources hoặc close trong finally.

## 3. TWR: các tài nguyên được mở trái sang phải, đóng phải sang trái

Cú pháp Java 17:

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    use(a, b, c);
}
~~~

Các biểu thức initializer chạy **từ trái sang phải**: A rồi B rồi C. Khi rời khối try, các tài nguyên **đã khởi tạo thành công** được close **theo thứ tự ngược lại**: C, B, A.

Nếu **openB() ném exception**:

~~~text
openA()  -> thành công
openB()  -> ném IOException
openC()  -> KHÔNG được gọi
use(...) -> KHÔNG được chạy
a.close()-> được gọi tự động
ngoại lệ từ openB() được truyền ra
~~~

Không có đối tượng b hoàn chỉnh để close; TWR chỉ chịu trách nhiệm với những resource initializer **đã trả về thành công**. Nếu openB() kịp tạo một raw stream bên trong rồi lỗi trước khi trả về b, **openB() phải cleanup raw stream đó**.

TWR áp dụng cho đối tượng triển khai **AutoCloseable** hoặc **Closeable**. Phương thức close() được gọi kể cả khi body throw, return hoặc có exception; **try-with-resources tự quản thứ tự đóng và suppressed exception**. Từ Java 9, có thể đặt biến đã khai báo trước trong ngoặc try nếu biến final hoặc effectively final, nhưng điều đó không tự làm thay đổi quyền sở hữu của biến.

## 4. Chương trình runnable: mở B lỗi, A vẫn được đóng

Tạo file **AcquisitionFailureDemo.java** (mã nguồn UTF-8):

~~~java
import java.io.IOException;

public class AcquisitionFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;
        private final boolean failClose;

        Resource(String name, boolean failClose) {
            this.name = name;
            this.failClose = failClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            if (failClose) {
                throw new IOException("close-" + name + " failed");
            }
        }
    }

    static Resource open(String name, boolean failClose)
            throws IOException {
        System.out.println("open:" + name);
        if ("B".equals(name)) {
            throw new IOException("open-B failed");
        }
        return new Resource(name, failClose);
    }

    public static void main(String[] args) {
        try (Resource a = open("A", true);
             Resource b = open("B", false)) {
            System.out.println("body");
        } catch (IOException primary) {
            System.out.println("primary=" + primary.getMessage());
            for (Throwable other : primary.getSuppressed()) {
                System.out.println("suppressed=" + other.getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 AcquisitionFailureDemo.java
java AcquisitionFailureDemo
~~~

Stdout dự kiến, đúng theo thứ tự gọi:

~~~text
open:A
open:B
close:A
primary=open-B failed
suppressed=close-A failed
~~~

Điểm cần quan sát:

- **open(A)** thành công nên A được đưa vào danh sách tài nguyên cần đóng.
- **open(B)** ném IOException; body chưa chạy (không có dòng body).
- A vẫn được close tự động ngay cả khi không vào body.
- close A **cũng thất bại**, nhưng exception của B vẫn là **primary**.
- IOException khi đóng A được gắn vào **primary.getSuppressed()**, nên có thể tìm lại cả hai vấn đề.

Nếu close A không thất bại thì danh sách suppressed rỗng; điều đó không ảnh hưởng cơ chế tự đóng. Nếu open B trả về thành công, B sẽ được đóng trước A lúc rời try.

## 5. Primary exception và suppressed exception

Khi hai lỗi cùng xuất hiện, phải quyết định **lỗi nào giải thích nguyên nhân chính**:

~~~text
Lỗi từ khởi tạo / body  -> primary exception
Lỗi trong close()       -> suppressed exception
~~~

Với TWR:

- Nếu initializer hoặc body ném lỗi và close cũng ném, lỗi ban đầu được giữ làm **primary**; các lỗi close được thêm vào danh sách suppressed.
- Nếu không có lỗi nào từ initializer/body nhưng close ném, lỗi close của tài nguyên đóng đầu tiên có thể trở thành primary; các lỗi close sau được suppressed.
- Các tài nguyên TWR còn lại vẫn được cố gắng close ngay cả khi close một tài nguyên trước đó thất bại.

Đây là ưu điểm lớn so với code thủ công kiểu:

~~~java
// SAI nếu muốn giữ nguyên lỗi nghiệp vụ:
try {
    work();
} finally {
    resource.close();
}
~~~

Nếu work() ném lỗi và resource.close() cũng ném, exception cuối có thể **che mất** exception từ work(). Ngoài ra, nếu close một tài nguyên trong finally ném lỗi, các lệnh cleanup phía sau nó có thể bị bỏ qua. Với TWR, Java thực hiện xử lý nhiều close và suppressed một cách nhất quán.

Để điều tra, log hoặc hiển thị cả **primary exception**, **cause chain** và **suppressed exceptions**. Chỉ lấy exception cuối cùng mà bỏ suppressed dễ khiến mất bằng chứng về resource cleanup thất bại.

**Suppressed không có nghĩa là lỗi không quan trọng**: một lần close thất bại có thể liên quan đến dữ liệu chưa flush hoặc tài nguyên chưa được giải phóng. Ứng dụng cần quy tắc xử lý phù hợp mức độ quan trọng của thao tác, nhưng vẫn giữ primary để định vị nguyên nhân đầu tiên.

## 6. Khi constructor của wrapper thất bại, TWR bên ngoài chưa đủ

Xét factory tạo raw stream, sau đó tạo wrapper:

~~~java
// Mảnh code minh họa ý tưởng, KHÔNG an toàn nếu bước wrap có thể lỗi.
InputStream raw = Files.newInputStream(path);
return createCustomWrapper(raw);
~~~

Nếu createCustomWrapper(raw) ném exception, phương thức không trả được wrapper và raw vẫn đang mở. Bên gọi không có wrapper để close. Cần đảm bảo **nếu chuyển ownership không thành công thì người mở raw vẫn tự đóng raw**.

Một kỹ thuật là giữ ownership ở factory trong lúc xây dựng, chỉ chuyển ownership sau khi tạo wrapper thành công:

~~~text
factory mở raw        -> factory đang sở hữu raw
factory tạo wrapper   -> có thể thành công/thất bại
  thành công          -> trả wrapper, chuyển ownership cho caller
  thất bại            -> factory close raw rồi rethrow lỗi gốc
caller close wrapper  -> wrapper close raw theo hợp đồng
~~~

Đối với Java wrapper chuẩn như BufferedInputStream, constructor đơn giản có thể không có IOException checked; nhưng một decorator tùy chỉnh có thể kiểm tra header, đọc metadata, mở file phụ hoặc ném exception. **Không dựa vào việc một constructor có vẻ đơn giản để bỏ qua nguyên tắc xử lý partial acquisition**.

## 7. Chương trình runnable: factory rollback khi wrapper lỗi

Tạo file **WrapperFactoryFailureDemo.java**:

~~~java
import java.io.IOException;

public class WrapperFactoryFailureDemo {
    static final class Handle implements AutoCloseable {
        Handle() {
            System.out.println("acquire:raw");
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:raw");
            throw new IOException("close-raw failed");
        }
    }

    static final class Wrapper implements AutoCloseable {
        private final Handle raw;

        Wrapper(Handle raw, boolean fail) throws IOException {
            System.out.println("construct:wrapper");
            if (fail) {
                throw new IOException("wrapper failed");
            }
            this.raw = raw;
        }

        @Override
        public void close() throws IOException {
            raw.close();
        }
    }

    static Wrapper create(boolean fail) throws IOException {
        Handle raw = new Handle();
        try {
            // Ownership chỉ chuyển cho Wrapper khi constructor trả về.
            return new Wrapper(raw, fail);
        } catch (IOException | RuntimeException | Error primary) {
            try {
                raw.close();
            } catch (Throwable cleanupFailure) {
                primary.addSuppressed(cleanupFailure);
            }
            throw primary;
        }
    }

    public static void main(String[] args) {
        try (Wrapper wrapper = create(true)) {
            System.out.println("body");
        } catch (IOException primary) {
            System.out.println("primary=" + primary.getMessage());
            for (Throwable other : primary.getSuppressed()) {
                System.out.println("suppressed=" + other.getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 WrapperFactoryFailureDemo.java
java WrapperFactoryFailureDemo
~~~

Stdout dự kiến:

~~~text
acquire:raw
construct:wrapper
close:raw
primary=wrapper failed
suppressed=close-raw failed
~~~

**Vì sao đúng?**

1. Handle được mở: factory đang giữ ownership.
2. Constructor Wrapper bắt đầu rồi ném IOException, nên **không có Wrapper hoàn chỉnh**; try-with-resources ở main không có resource để đóng.
3. Factory bắt lỗi mở/wrap, cố close Handle trước khi trả lỗi cho caller.
4. Nếu close Handle cũng ném, factory thêm lỗi cleanup vào **suppressed của exception gốc**, không thay thế nguyên nhân thất bại wrapper.
5. Nếu Wrapper được tạo thành công, factory trả Wrapper và caller có trách nhiệm đóng nó; factory không đóng raw ở đường thành công vì wrapper đã sở hữu raw.

Trong factory này, nhánh catch bao gồm IOException, RuntimeException, Error phát sinh từ construction; `Throwable` ở catch nội bộ chỉ nhằm **giữ lại lỗi cleanup** làm suppressed. Trong ứng dụng thực tế cần cân nhắc các lỗi nghiêm trọng như VirtualMachineError, ThreadDeath và quy định exception của API. Đây là mẫu giải thích ownership/cleanup, không phải lời khuyên bắt mọi Throwable rồi tiếp tục chạy bình thường.

**Ràng buộc thiết kế:** ví dụ giả định wrapper **không tự đóng raw khi constructor thất bại**. Nếu một wrapper đã sở hữu rồi tự cleanup raw trước khi ném, factory và wrapper phải thống nhất hợp đồng tránh double-close. Tránh mặc định close() của mọi tài nguyên đều gọi lặp an toàn.

## 8. Tự cleanup khi constructor mở nhiều tài nguyên nội bộ

Một constructor có thể mở A rồi B trước khi object tạo thành công:

~~~text
new Composite():
    open A          -> thành công
    open B          -> lỗi
    chưa có Composite để caller.close()
~~~

Bên gọi không thể dùng try-with-resources để đóng một instance Composite **chưa bao giờ được trả về**. Constructor hoặc factory xây dựng Composite phải đặt ownership của A trong một vùng cleanup trước khi thử B.

Một giải pháp đáng tin hơn trong nhiều thiết kế là tách **factory acquire resources** khỏi **constructor gắn các reference đã hợp lệ**, hoặc dùng TWR có phạm vi rõ. Mẫu pseudo-code có cấu trúc:

~~~java
// Mảnh code: createComposite nhận trách nhiệm sở hữu tài nguyên
// trong lúc xây dựng. Kiểu A/B/Composite giả định có API tương ứng.
A a = openA();
try {
    B b = openB();
    try {
        return new Composite(a, b); // Chuyển ownership nếu thành công
    } catch (IOException | RuntimeException | Error primary) {
        try {
            b.close();
        } catch (Throwable cleanup) {
            primary.addSuppressed(cleanup);
        }
        throw primary;
    }
} catch (IOException | RuntimeException | Error primary) {
    try {
        a.close();
    } catch (Throwable cleanup) {
        primary.addSuppressed(cleanup);
    }
    throw primary;
}
~~~

Đây là **mảnh code minh họa**, các kiểu A, B, Composite và openA/openB được ứng dụng định nghĩa. Mục đích là thấy vùng sở hữu A và B, và cơ chế rollback khi từng bước thất bại. Với API thực tế, nên đóng gói logic này thành factory rõ contract, test đủ failure path, tránh lặp nhiều khối catch rối.

Quan trọng: nếu constructor của B **tự mở một handle rồi ném** trước khi trả về B, chính constructor/factory của B phải cleanup handle ấy. Vòng catch phía ngoài chỉ đóng được A hoặc những B đã trả về thành công.

### Cách dùng TWR khi kết quả không cần sống ngoài block

Nếu các tài nguyên chỉ phục vụ một thao tác cục bộ, TWR là lựa chọn đơn giản nhất:

~~~java
// Mảnh code trong phương thức có Path source, target.
try (var input = java.nio.file.Files.newInputStream(source);
     var output = java.nio.file.Files.newOutputStream(target)) {
    input.transferTo(output);
}
~~~

Nếu mở output thất bại, input được đóng tự động. Nếu quá trình copy lỗi, cả output và input vẫn được thử đóng theo thứ tự ngược lại. Trong trường hợp này **không cần chuyển ownership của stream ra ngoài**.

Ngược lại, nếu cần **trả wrapper ra ngoài** để caller dùng sau khi factory kết thúc, không được đặt raw stream trong TWR mà luôn close khi rời factory. Ví dụ trả `new BufferedInputStream(raw)` từ bên trong `try (raw)` sẽ trả một wrapper đã có stream nền bị đóng. Cần dùng mẫu factory transfer ownership đã mô tả.

## 9. Khi close() của wrapper sở hữu stream bên dưới

Nhiều wrapper chuẩn của Java đóng luôn stream được bọc:

~~~java
// Mảnh code: BufferedInputStream sở hữu raw bên dưới.
InputStream raw = Files.newInputStream(path);
BufferedInputStream wrapped = new BufferedInputStream(raw);
wrapped.close(); // Thường đóng cả raw qua wrapper.
~~~

Khi ownership đã chuyển vào wrapped, caller nên **đóng wrapped** thay vì đóng cả wrapped và raw một cách độc lập. TWR có hai resource lồng nhau có thể double-close raw nếu wrapper đã đóng nó trước:

~~~java
// Cần hiểu rõ contract vì raw có thể bị close hai lần:
try (InputStream raw = Files.newInputStream(path);
     BufferedInputStream wrapped = new BufferedInputStream(raw)) {
    // ...
}
~~~

Trong thư viện chuẩn có loại stream chịu được close lặp, nhưng với custom AutoCloseable, double-close có thể không an toàn hoặc gây side effect. Nếu mục tiêu là khắc phục thất bại lúc tạo wrapper, hãy dùng contract ownership và factory rollback rõ ràng.

**Không nên thiết kế custom wrapper mà đóng tài nguyên của caller nếu caller chỉ cho mượn tài nguyên**, trừ khi API ghi rõ điều này. Nếu wrapper chỉ borrow raw, caller vẫn đóng raw theo hợp đồng của mình; chọn một convention và dùng nhất quán.

## 10. Dọn file tạm và side effect khi tạo nhiều tài nguyên

Với Java I/O, resource không chỉ là stream. Một thao tác có thể:

1. Tạo thư mục/file tạm.
2. Mở output stream để ghi.
3. Tạo stream bọc nén hoặc mã hóa.
4. Ghi dữ liệu.
5. Đổi tên file tạm sang file đích.

Nếu bước 2–4 lỗi, đóng stream thôi **chưa chắc xóa file tạm**. Cần **compensating cleanup** cho side effect: xóa file tạm của chính thao tác đó, nhưng chỉ khi chắc chắn nó do thao tác tạo và chưa được chuyển quyền cho nơi khác.

Ví dụ mô hình:

~~~text
tạo file temp -> ghi vào temp -> đóng thành công
                   |                 |
                   | lỗi             v
                   v              publish/rename
              đóng stream             |
              xóa temp nếu còn        v
                                 file kết quả
~~~

Sử dụng `Files.deleteIfExists(temp)` trong cleanup thích hợp; nếu thao tác xóa thất bại, cũng cần giữ lại lỗi gốc và ghi nhận lỗi dọn dẹp. Tránh xóa file đích hoặc dữ liệu đã tồn tại trước khi tác vụ bắt đầu. Với thao tác publish/rename, yêu cầu tính nguyên tử và độ bền dữ liệu còn phụ thuộc filesystem cùng thiết kế riêng.

**Cleanup không đồng nghĩa rollback mọi thay đổi:** close của một OutputStream không khôi phục nội dung file đã ghi một phần. Nếu dữ liệu cần tính toàn vẹn, nên xây dựng bằng file tạm, xác minh thành công rồi mới publish.

## 11. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Mở A, B rồi mới bắt đầu try/finally | Nếu B lỗi, A có thể leak | Bắt đầu TWR từ resource A hoặc có cleanup rollback |
| Tưởng TWR đóng cả object constructor chưa trả về | Handle nội bộ vẫn có thể leak | Constructor/factory tự cleanup các resource đã tạo |
| Close trong finally ném và che mất lỗi gốc | Mất nguyên nhân lỗi chính | Ưu tiên TWR và suppressed exceptions |
| Trả wrapper từ factory trong TWR đang sở hữu raw | Raw bị đóng trước khi caller dùng | Transfer ownership khi factory trả thành công |
| Wrapper + caller cùng close stream nền | Có thể double-close | Công bố một owner rõ ràng |
| Không close nguồn khi tạo wrapper ném exception | Resource leak | Catch, close nguồn, rethrow primary |
| Bỏ qua getSuppressed() | Mất thông tin lỗi close | Kiểm tra primary, cause và suppressed |
| Catch exception rồi chỉ log, tiếp tục trả object nửa khởi tạo | Object không hợp lệ | Rollback rồi rethrow |
| Coi close không thể thất bại | Mất lỗi flush, đóng file/socket | Có chính sách xử lý IOException khi close |
| Đóng resource sai thứ tự phụ thuộc | Wrapper dùng raw đã đóng | Đóng theo reverse ownership/dependency |
| Chỉ close stream nhưng giữ file tạm hỏng | Rác file hoặc dữ liệu dở dang | Cleanup cả side effect do tác vụ sở hữu |
| Dựa vào GC để đóng I/O | Không bảo đảm thời điểm giải phóng | TWR/close chủ động |

## 12. Quy trình thiết kế và kiểm tra

Khi viết code xây dựng/ghép tài nguyên, tự trả lời:

1. **Mỗi bước tạo cái gì?** File descriptor, stream, buffer, file tạm, socket, lock...
2. **Ai sở hữu sau khi bước tạo thành công?** Factory hay đối tượng wrapper?
3. **Điều gì xảy ra nếu bước tiếp theo lỗi?** Tài nguyên tạo trước được close ở đâu?
4. **Nếu close cũng lỗi thì sao?** Primary exception được giữ nguyên, cleanup exception được suppressed hay báo cáo riêng theo contract?
5. **Khi thành công, ai đóng cuối cùng?** Caller nhận ownership qua return hay phương thức tự đóng trong scope?
6. **Có side effect khác ngoài tài nguyên đóng được không?** File tạm, transaction, rename, trạng thái external...
7. **Có test mô phỏng từng điểm thất bại không?** Lỗi mở A, lỗi mở B, lỗi wrap, lỗi body, lỗi close A/B, và trường hợp hai lỗi đồng thời.

Với tài nguyên nhiều tầng, vẽ **sơ đồ ownership** trước khi tối ưu. Trong một luồng đơn giản, TWR có thể xử lý hoàn chỉnh; trong factory trả wrapper ra ngoài, cần có thời điểm chuyển quyền rõ ràng. Không nên thêm catch chỉ để đóng resource đã được TWR đóng, vì có thể tạo double-close và che lỗi.

### Kiểm tra hành vi theo tình huống

| Tình huống | Hành vi cần có |
| --- | --- |
| Mở A thất bại trước khi A được tạo | Không có A để đóng; A factory phải tự dọn phần đã mở nội bộ |
| Mở A thành công, mở B lỗi | A được đóng, lỗi B được giữ |
| Body lỗi, close B và A đều lỗi | Lỗi body là primary, lỗi close của B và A là suppressed |
| Body thành công, close B lỗi, close A thành công | Lỗi close B được báo, A vẫn được close |
| Wrapper construction lỗi sau khi raw mở | Raw được đóng theo quyền sở hữu của factory |
| Wrapper construction thành công | Caller đóng wrapper; wrapper đóng raw nếu sở hữu |
| Tạo file tạm thành công nhưng ghi thất bại | Stream được đóng; file tạm của tác vụ được cleanup |
| Cleanup cũng lỗi | Giữ đầy đủ primary và cleanup failure; không tuyên bố hoàn tất thành công |

## 13. Bài tập tự kiểm tra

**Câu 1.** Trong `try (A a = openA(); B b = openB())`, nếu openB ném IOException thì A có được đóng không?  
**Đáp án:** Có, nếu openA đã trả về A thành công. TWR đóng A khi initializer B thất bại.

**Câu 2.** Nếu constructor B đã mở một Socket rồi ném trước khi trả về B thì TWR bên gọi có đóng Socket được không?  
**Đáp án:** Không tự động. B chưa được tạo xong, nên constructor/factory B phải cleanup Socket nội bộ.

**Câu 3.** Body ném IOException, A.close cũng ném IOException: lỗi nào là primary trong TWR?  
**Đáp án:** Lỗi từ body vẫn là primary; lỗi close được đặt trong getSuppressed().

**Câu 4.** Factory mở InputStream rồi tạo wrapper. Nếu wrapper khởi tạo thất bại thì owner nào phải đóng InputStream?  
**Đáp án:** Factory vẫn sở hữu cho đến khi wrapper được trả về thành công; factory phải đóng InputStream và truyền lại lỗi gốc.

**Câu 5.** Có nên dùng `try (InputStream raw = openRaw()) { return new BufferedInputStream(raw); }` không?  
**Đáp án:** Không nếu wrapper được trả về để caller đọc sau đó; raw đã bị đóng khi rời try, nên wrapper không còn nguồn mở.

**Câu 6.** Đóng wrapper và raw cùng lúc có luôn an toàn không?  
**Đáp án:** Không. Wrapper có thể đã đóng raw; custom resource có thể không hỗ trợ double-close. Cần một quy tắc ownership rõ.

**Câu 7.** Nếu tác vụ ghi dở file tạm rồi IOException, chỉ close OutputStream đã đủ rollback chưa?  
**Đáp án:** Chưa. Close không xóa hoặc khôi phục nội dung file; có thể cần xóa file tạm và chỉ publish khi ghi hoàn chỉnh.

## 14. Tài liệu Java SE 17 để tra cứu

- [AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng close; có loại resource không hỗ trợ close lặp an toàn.
- [Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): giao diện close cho I/O.
- [Java Tutorial — try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): đóng tài nguyên theo thứ tự ngược, suppressed exceptions.
- [Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): xem lỗi phụ xảy ra trong cleanup.
- [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html): ví dụ wrapper sở hữu input stream bên dưới.

**Ghi nhớ:** TWR tự đóng các resource **đã khởi tạo thành công** khi những bước sau thất bại, đồng thời giữ primary và suppressed exceptions. Nhưng nếu một constructor/factory mở resource nội bộ rồi thất bại trước khi trả về object, phần **cleanup nội bộ là trách nhiệm của chính constructor/factory**. Khi ghép stream, hãy quy định rõ lúc nào ownership được chuyển; khi cleanup thất bại, bảo toàn lỗi gốc cùng thông tin về lỗi close.
