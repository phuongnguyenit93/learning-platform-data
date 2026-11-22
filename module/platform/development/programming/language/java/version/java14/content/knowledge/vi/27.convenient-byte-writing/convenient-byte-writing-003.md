# Quan hệ giữa `ByteArrayOutputStream.writeBytes(byte[])` và `write(byte[], int, int)`

## 1. Trọng tâm: một cách ghi toàn bộ, một cách ghi theo đoạn

Khi làm việc với `java.io.ByteArrayOutputStream`, lập trình viên thường gặp hai cách ghi từ một mảng byte:

~~~java
out.writeBytes(data);
out.write(data, 0, data.length);
~~~

**Đối với `ByteArrayOutputStream`, hai câu lệnh trên có hiệu ứng tương đương nếu thực hiện riêng rẽ từ cùng trạng thái ban đầu.** Đây không chỉ là suy luận về kết quả: Javadoc của Java SE 14, 17 và 26 ghi rõ trong phần **API Note** của `writeBytes(byte[])` rằng phương thức này tương đương `write(b, 0, b.length)`.

Trong khi đó:

~~~java
out.write(data, offset, length);
~~~

ghi **chỉ `length` byte**, bắt đầu ở vị trí **`offset` trong mảng đầu vào**. `offset` không phải vị trí trong bộ đệm đích; `ByteArrayOutputStream` luôn **nối** các byte được ghi vào cuối dữ liệu đã chứa.

Như vậy:

- **Ghi toàn bộ byte array:** dùng `writeBytes(data)` khi biến `out` có kiểu `ByteArrayOutputStream`.
- **Ghi một lát cắt:** dùng `write(data, offset, length)`.
- **Muốn ghi toàn bộ nhưng chỉ làm việc qua kiểu `OutputStream` chung:** dùng `write(data)` hoặc `write(data, 0, data.length)`; đừng gọi `writeBytes(data)` trên biến `OutputStream` vì phương thức đó **không được khai báo trong `OutputStream`**.

**Phiên bản và tính hiện hành:** `ByteArrayOutputStream.writeBytes(byte[])` được bổ sung từ **Java 11**, không phải API mới riêng của Java 14. Nó vẫn có mặt trong tài liệu Java 26 và dùng được trong dự án Java 17+. Bài học chỉ dùng các API còn hiệu lực; không cần cơ chế cũ hoặc kỹ thuật đã deprecated.

## 2. Đúng class, đúng chữ ký phương thức

Ba khai báo thường gây nhầm:

~~~java
// java.io.ByteArrayOutputStream, since Java 11
public void writeBytes(byte[] b);

// java.io.ByteArrayOutputStream, override từ OutputStream
public synchronized void write(byte[] b, int off, int len);

// java.io.OutputStream
public void write(byte[] b) throws IOException;
~~~

Đây là **chữ ký minh họa**, không phải một file Java biên dịch độc lập. Javadoc là nguồn chuẩn về hợp đồng API; cú pháp `synchronized` thể hiện cách `ByteArrayOutputStream` cung cấp `write(byte[], int, int)` trong OpenJDK. Khi viết mã ứng dụng, chỉ cần gọi các phương thức trên instance, không tự sao chép chữ ký.

### Một bảng đối chiếu

| Phương thức | Class công bố | Byte được ghi | Offset/length | `IOException` checked tại call site |
| --- | --- | --- | --- | --- |
| `ByteArrayOutputStream.writeBytes(b)` | `ByteArrayOutputStream` | Toàn bộ `b[0..b.length-1]` | Không truyền | **Không** |
| `ByteArrayOutputStream.write(b, off, len)` | Override trong `ByteArrayOutputStream` | `b[off]` đến `b[off+len-1]` | Có | **Không** |
| `OutputStream.write(b)` | `OutputStream` | Toàn bộ mảng | Không truyền | **Có** theo chữ ký `OutputStream` |
| `OutputStream.write(b, off, len)` | `OutputStream`, có thể được override | Một lát cắt | Có | **Có** theo chữ ký `OutputStream` |

**Phân biệt biên dịch và runtime:** một `ByteArrayOutputStream` không dùng file/socket để ghi; hai phương thức `writeBytes(b)` và `write(b,off,len)` của class này không khai báo `IOException`. Nhưng nếu bạn giữ cùng object dưới biến kiểu **`OutputStream`**, compiler dựa trên **chữ ký của `OutputStream`**, vốn khai báo `throws IOException` cho các overload `write`. Đây là vấn đề **kiểu tĩnh của biến**, không phải object thật tự nhiên bắt đầu ghi dữ liệu ra ổ đĩa.

### Ý nghĩa chính xác của `off` và `len`

Cho mảng:

~~~text
index:   0   1   2   3   4
value:   A   B   C   D   E
~~~

Khi gọi:

~~~java
out.write(data, 1, 3);
~~~

sẽ lấy **B, C, D** vì `off=1` và `len=3`. Byte ở vị trí `off+len` (E, index 4) **không thuộc lát cắt**.

Hãy hình dung đoạn nửa mở:

~~~text
[off, off + len)
~~~

Với một mảng có độ dài `n`, dải hợp lệ phải đáp ứng:

~~~text
0 <= off <= n
0 <= len
len <= n - off
~~~

Viết điều kiện `len <= n-off` thay vì chỉ cộng `off+len` trong code tự kiểm tra có thể giúp tránh lỗi tràn số nguyên khi đầu vào có giá trị lớn. Bản thân JDK đã định nghĩa ngoại lệ cho các trường hợp không hợp lệ; code ứng dụng thường không cần viết lại logic kiểm tra này.

## 3. Quan hệ tương đương nằm ở dữ liệu được thêm, không phải ở việc gọi hai lần

Hai cách viết sau là **hai lựa chọn thay thế**:

~~~java
// Lựa chọn A:
ByteArrayOutputStream a = new ByteArrayOutputStream();
a.writeBytes(data);

// Lựa chọn B:
ByteArrayOutputStream b = new ByteArrayOutputStream();
b.write(data, 0, data.length);
~~~

Khi `data` chứa cùng nội dung và hai output stream bắt đầu với cùng trạng thái, `a.toByteArray()` và `b.toByteArray()` có dữ liệu byte giống nhau.

Nhưng **nếu chạy cả hai câu lệnh trên cùng một stream**, byte sẽ được nối **hai lần**:

~~~java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.writeBytes(data);
out.write(data, 0, data.length);
~~~

Kết quả sau hai lệnh là **`data` nối với `data`**, không phải một phép ghi bị JDK tự tối ưu để tránh trùng lặp. `ByteArrayOutputStream` là buffer có trạng thái; mỗi lệnh ghi thay đổi số byte đang chứa.

**Quy tắc API:** `writeBytes(b)` ghi **toàn bộ** mảng được truyền vào. Nó không tự tìm byte kết thúc, ký tự `'\0'`, dấu xuống dòng, phân tách gói tin hay một phần mảng được cho là “hợp lệ”. Nếu bạn chỉ muốn một phần, phải dùng overload ba tham số hoặc tạo một lát cắt byte mới theo nhu cầu.

## 4. Ví dụ Java 17+ số 1: cùng nội dung khi ghi toàn bộ, khác nội dung khi ghi lát cắt

Tạo file **`WriteBytesRelationDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class WriteBytesRelationDemo {
    static class TracingOutput extends ByteArrayOutputStream {
        int sliceCalls;
        int lastOffset;
        int lastLength;

        @Override
        public synchronized void write(byte[] b, int off, int len) {
            sliceCalls++;
            lastOffset = off;
            lastLength = len;
            super.write(b, off, len);
        }
    }

    public static void main(String[] args) {
        byte[] source = "ABCDE".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream complete = new ByteArrayOutputStream();
        ByteArrayOutputStream rangeEquivalent = new ByteArrayOutputStream();
        ByteArrayOutputStream sliced = new ByteArrayOutputStream();

        complete.writeBytes(source);
        rangeEquivalent.write(source, 0, source.length);
        sliced.write(source, 1, 3);

        System.out.println("equivalent="
                + Arrays.equals(complete.toByteArray(),
                        rangeEquivalent.toByteArray()));
        System.out.println("whole="
                + complete.toString(StandardCharsets.UTF_8));
        System.out.println("slice="
                + sliced.toString(StandardCharsets.UTF_8));

        int before = complete.size();
        complete.writeBytes(new byte[0]);
        System.out.println("emptyKeepsSize=" + (before == complete.size()));

        source[0] = 'Z';
        System.out.println("inputMutationDoesNotChangeStoredBytes="
                + (complete.toByteArray()[0] == (byte) 'A'));

        complete.writeBytes(new byte[] {(byte) 0xff, 0});
        System.out.println("binaryHex="
                + HexFormat.of().formatHex(complete.toByteArray()));

        sliced.write(source, 0, 1);
        System.out.println("sliceThenAppend="
                + sliced.toString(StandardCharsets.UTF_8));

        TracingOutput tracing = new TracingOutput();
        tracing.writeBytes(new byte[] {1, 2, 3});
        System.out.println("writeBytesDelegatedToSlice="
                + (tracing.sliceCalls == 1));
        System.out.println("delegatedOffset=" + tracing.lastOffset);
        System.out.println("delegatedLength=" + tracing.lastLength);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 WriteBytesRelationDemo.java
java WriteBytesRelationDemo
~~~

**Stdout đã kiểm chứng bằng `javac --release 17`:**

~~~text
equivalent=true
whole=ABCDE
slice=BCD
emptyKeepsSize=true
inputMutationDoesNotChangeStoredBytes=true
binaryHex=4142434445ff00
sliceThenAppend=BCDZ
writeBytesDelegatedToSlice=true
delegatedOffset=0
delegatedLength=3
~~~

### Vì sao có những kết quả đó?

**`equivalent=true`:** `writeBytes(source)` thêm năm byte `A B C D E`; `write(source, 0, source.length)` cũng thêm đúng năm byte đó. `Arrays.equals` xác nhận hai mảng kết quả trùng nhau tại mọi vị trí.

**`whole=ABCDE` và `slice=BCD`:** `write(source,1,3)` bắt đầu từ index 1 trong source, lấy ba byte liên tiếp. Nó **không** ghi byte A hoặc E.

**`emptyKeepsSize=true`:** mảng dài 0 không đóng góp byte nào. Đây vẫn là lệnh gọi hợp lệ; `ByteArrayOutputStream` giữ nguyên số byte có hiệu lực.

**`inputMutationDoesNotChangeStoredBytes=true`:** sau khi ghi xong, code sửa `source[0]` thành Z. Dữ liệu đã chép vào `complete` vẫn bắt đầu bằng A. `ByteArrayOutputStream` **chép** các byte được ghi vào buffer nội bộ; không giữ view trỏ trực tiếp vào mảng đầu vào chỉ vì bạn gọi `writeBytes`. Đây là kiểm tra quan trọng để tránh nhầm về ownership bộ nhớ.

**`binaryHex=4142434445ff00`:** sau khi ghi ABCDE, code nối thêm byte nhị phân `FF 00`. `writeBytes` **không diễn dịch** dữ liệu là text và **không dừng tại byte `00`**. Kết quả hex đúng là `41 42 43 44 45 FF 00`.

**`sliceThenAppend=BCDZ`:** biến `sliced` trước đó chứa BCD. Sau khi source bị sửa thành ZBCDE, `sliced.write(source,0,1)` nối byte Z vào **cuối** buffer. Tham số `off=0` chọn byte ở index 0 của **mảng nguồn**, không ghi đè index 0 của buffer đích.

**Ba dòng `TracingOutput`:** subclass override `write(byte[],off,len)`. Khi gọi `writeBytes(new byte[]{1,2,3})`, method được chuyển qua đường `write(b,0,b.length)` như Javadoc mô tả, nên subclass ghi nhận **một lần gọi lát cắt** với `off=0`, `len=3`. Đây là cách quan sát quan hệ giữa hai method mà không dựa vào suy đoán hiệu suất.

**Lưu ý về `HexFormat`:** class này có từ Java 17, nên chương trình được cố ý đặt mục tiêu `--release 17`. Nhưng riêng `ByteArrayOutputStream.writeBytes` đã có từ Java 11; không nên suy luận nó chỉ có ở Java 17.

## 5. Ranh giới hợp lệ và ngoại lệ

Khi gọi `write(byte[], int, int)`, các điều kiện thường phải nhớ là:

| Trường hợp | Kết quả với `ByteArrayOutputStream` |
| --- | --- |
| `b` khác `null`, `off=0`, `len=b.length` | Ghi toàn bộ byte |
| `b` khác `null`, `off>0`, `len` hợp lệ | Ghi đoạn con được chọn |
| `b.length=0`, gọi `writeBytes(b)` | Hợp lệ, không thêm byte |
| `off=b.length`, `len=0` | Hợp lệ, không thêm byte |
| `off<0` | `IndexOutOfBoundsException` |
| `len<0` | `IndexOutOfBoundsException` |
| `len>b.length-off` | `IndexOutOfBoundsException` |
| `b==null`, gọi `writeBytes(b)` | `NullPointerException` |
| `b==null`, gọi `write(b,off,len)` | `NullPointerException` |

Hai điểm dễ nhầm:

- **`off=b.length, len=0` được phép:** đoạn trống ở ngay cuối mảng là hợp lệ. Ngược lại `off=b.length, len=1` là vượt ranh giới.
- **`len` không phải index kết thúc:** ví dụ `write(b,2,2)` lấy index 2 và 3. Nếu muốn lấy vùng [2,5) thì phải dùng `write(b,2,3)`, không phải `write(b,2,5)`.

Với `writeBytes(b)`, bạn **không có tham số offset/length** để truyền sai. Nhưng nó vẫn ném `NullPointerException` khi `b==null` và có thể cần thêm bộ nhớ nếu buffer phải lớn lên để chứa dữ liệu.

Đừng catch `IndexOutOfBoundsException` rồi im lặng để “ghi phần nào có thể”. Cần tính đúng lát cắt từ đầu hoặc kiểm tra dữ liệu đầu vào để tránh ghi sai định dạng gói tin/file.

## 6. Ví dụ Java 17+ số 2: ngoại lệ, byte nhị phân và mã hóa Unicode

Tạo file **`WriteBytesBoundaryDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class WriteBytesBoundaryDemo {
    static String errorName(Runnable code) {
        try {
            code.run();
            return "none";
        } catch (RuntimeException failure) {
            return failure.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] source = {10, 20, 30, 40};
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        output.write(source, source.length, 0);
        System.out.println("zeroLengthAtEnd=" + output.size());
        output.write(source, 2, 2);
        output.writeBytes(source);
        System.out.println("rangeThenWholeHex="
                + HexFormat.of().formatHex(output.toByteArray()));

        System.out.println("nullWhole="
                + errorName(() -> output.writeBytes(null)));
        System.out.println("nullSlice="
                + errorName(() -> output.write(null, 0, 0)));
        System.out.println("negativeOffset="
                + errorName(() -> output.write(source, -1, 1)));
        System.out.println("negativeLength="
                + errorName(() -> output.write(source, 0, -1)));
        System.out.println("pastEnd="
                + errorName(() -> output.write(source, 3, 2)));

        String text = "đ";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        encoded.writeBytes(utf8);
        System.out.println("charCount=" + text.length());
        System.out.println("utf8ByteCount=" + encoded.size());
        System.out.println("decoded="
                + encoded.toString(StandardCharsets.UTF_8));

        ByteArrayOutputStream receiver = new ByteArrayOutputStream();
        encoded.writeTo(receiver);
        System.out.println("writeToPreservesBytes="
                + java.util.Arrays.equals(encoded.toByteArray(),
                        receiver.toByteArray()));
        encoded.reset();
        System.out.println("sizeAfterReset=" + encoded.size());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 WriteBytesBoundaryDemo.java
java WriteBytesBoundaryDemo
~~~

**Stdout đã được kiểm thử:**

~~~text
zeroLengthAtEnd=0
rangeThenWholeHex=1e280a141e28
nullWhole=NullPointerException
nullSlice=NullPointerException
negativeOffset=IndexOutOfBoundsException
negativeLength=IndexOutOfBoundsException
pastEnd=IndexOutOfBoundsException
charCount=1
utf8ByteCount=2
decoded=đ
writeToPreservesBytes=true
sizeAfterReset=0
~~~

### Phân tích ranh giới

- `output.write(source,source.length,0)` ghi **0 byte**, nên `size()` vẫn là 0. `off` bằng đúng độ dài mảng là hợp lệ **khi `len=0`**.
- `output.write(source,2,2)` thêm các byte decimal 30, 40, tương ứng hex `1E 28`.
- `output.writeBytes(source)` nối toàn bộ bốn byte 10, 20, 30, 40, tương ứng hex `0A 14 1E 28`. Vì nối theo thứ tự nên kết quả chung là **`1E 28 0A 14 1E 28`**.
- `nullWhole` và `nullSlice` minh họa **cùng loại `NullPointerException`** khi mảng là `null`. Đừng coi `len=0` là cách bỏ qua việc kiểm tra `b==null`.
- `negativeOffset`, `negativeLength` và `pastEnd` cho thấy ba loại điều kiện phạm vi không hợp lệ. Helper `errorName` chỉ để in tên exception dễ đọc trong bài; code ứng dụng thật cần validate/thiết kế dữ liệu đầu vào phù hợp, không nên dùng exception như luồng điều khiển thông thường.
- `String "đ"` có **1 UTF-16 code unit** nhưng cần **2 byte** trong UTF-8. `ByteArrayOutputStream.writeBytes` xử lý **byte**, hoàn toàn không tự mã hóa ký tự. Code gọi `getBytes(StandardCharsets.UTF_8)` trước để quy định charset.
- `writeTo(receiver)` là phương thức **khác**: nó chép **dữ liệu đang chứa trong ByteArrayOutputStream nguồn** ra một `OutputStream` đích. Ngược lại `writeBytes(sourceArray)` **nạp byte từ mảng vào ByteArrayOutputStream nhận**. Hai tên trông gần nhau nhưng chiều dữ liệu khác nhau.
- `reset()` làm `size()` trở thành 0 và cho phép dùng lại buffer. Nó không hoàn nguyên các byte đã được ghi ra `receiver` trong ví dụ.

## 7. `write(byte[])` từ OutputStream: cùng ý nghĩa nhưng khác API owner

Ngoài `writeBytes(b)` và `write(b,off,len)`, còn một overload dễ bị nhầm:

~~~java
OutputStream destination = new ByteArrayOutputStream();
destination.write(bytes);
~~~

Đoạn trên là **mã minh họa trong phương thức cho phép `IOException`** (và cần import `OutputStream`, `ByteArrayOutputStream`). `OutputStream.write(byte[])` có hợp đồng ghi **toàn bộ** byte array, tương đương `write(b,0,b.length)`. Vì thế với object `ByteArrayOutputStream`, kết quả dữ liệu sẽ giống `writeBytes(b)` khi cùng trạng thái đầu vào.

Nhưng khác nhau ở **kiểu dữ liệu được khai báo**:

~~~java
ByteArrayOutputStream specific = new ByteArrayOutputStream();
specific.writeBytes(bytes);       // Có: method riêng ByteArrayOutputStream
specific.write(bytes, 0, bytes.length);

OutputStream generic = specific;
generic.write(bytes);            // Có: method của OutputStream
generic.write(bytes, 0, bytes.length);
// generic.writeBytes(bytes);    // KHÔNG biên dịch: OutputStream không có method này
~~~

Đoạn trên là **minh họa**, dùng biến `bytes` do người gọi chuẩn bị, và cần xử lý `IOException` cho các lệnh qua `generic`. Lệnh cuối được chú thích cố ý để không khiến file Java lỗi biên dịch.

Sự khác biệt:

1. **`ByteArrayOutputStream.writeBytes(byte[])`** trả `void`, **không khai báo `throws IOException`**.
2. **`ByteArrayOutputStream.write(byte[],off,len)`** trả `void`, cũng **không khai báo checked `IOException`**.
3. **`OutputStream.write(byte[])`** và **`OutputStream.write(byte[],off,len)`** trong interface API của `OutputStream` có `throws IOException`; nếu biến có kiểu tĩnh `OutputStream`, caller phải xử lý/khai báo ngoại lệ phù hợp ngay cả khi object runtime là BAOS.
4. **Không có `OutputStream.writeBytes(byte[])`** trong Java SE. Đừng tự khẳng định mọi stream con đều có tiện ích BAOS này.

Nếu viết thư viện xử lý **nhiều loại OutputStream**, hãy nhận `OutputStream` và dùng `write(byte[])` hoặc `write(byte[],off,len)`. Nếu đang xây dựng dữ liệu **trong bộ nhớ** và dùng trực tiếp `ByteArrayOutputStream`, `writeBytes` là lựa chọn gọn, rõ ràng.

### Khi nào cần ép kiểu?

Có thể ép `OutputStream` sang `ByteArrayOutputStream` nếu bạn **biết chính xác object thực** là BAOS. Tuy nhiên việc ép chỉ để gọi `writeBytes` thường không đáng vì `OutputStream.write(bytes)` đã có hợp đồng ghi toàn bộ. Không nên viết code thư viện phụ thuộc `instanceof ByteArrayOutputStream` chỉ để tránh một overload chuẩn trừ khi có lý do thiết kế rõ ràng.

## 8. Tính đa hình: vì sao writeBytes có thể gọi override của write(…, off, len)?

Javadoc `ByteArrayOutputStream.writeBytes(byte[])` quy định quan hệ tương đương với `write(b,0,b.length)`. Trong triển khai OpenJDK, `writeBytes(b)` gọi phương thức `write(b,0,b.length)`.

Vì `write(byte[],int,int)` là phương thức instance được override được, một subclass có thể ghi nhận lời gọi này. Trong `WriteBytesRelationDemo`, `TracingOutput` đã làm đúng điều đó:

~~~java
static class TracingOutput extends ByteArrayOutputStream {
    int calls;

    @Override
    public synchronized void write(byte[] b, int off, int len) {
        calls++;
        super.write(b, off, len);
    }
}
~~~

Đây là **trích đoạn** từ chương trình đầy đủ ở phần 4, không phải class có `main`. Khi gọi `tracing.writeBytes(byte[])`, biến `calls` tăng một lần trong triển khai đã được kiểm thử.

**Điểm thiết kế:** nếu mở rộng `ByteArrayOutputStream` và override phương thức ghi theo lát cắt, phải tôn trọng hợp đồng về thứ tự, nội dung, kiểm tra phạm vi và trạng thái; đừng tự thay semantics vì một lớp khác có thể dựa vào `writeBytes`. Phương thức `writeBytes` **không phải một phương thức ghi dữ liệu vòng qua mọi kiểm tra mà subclass đã định nghĩa**.

Bản thân **việc override** không nên dùng làm cớ để tối ưu khi chưa đo. Phương thức BAOS chuẩn đã hỗ trợ ghi cả mảng byte hiệu quả bằng cách sao chép vào buffer, thay vì chỉ dựa trên vòng lặp ghi một byte một lần của implementation mặc định `OutputStream`.

## 9. Ghi dữ liệu nhị phân và UTF-8: byte không phải ký tự

`writeBytes(byte[])` ghi **byte đúng như chúng có**. Nó không tự:

- chọn charset;
- thêm byte kết thúc 0;
- thêm newline;
- chèn length-prefix;
- escape ký tự đặc biệt;
- chuyển số `byte` âm trong Java thành một định dạng text;
- phân biệt header với payload.

Ví dụ:

~~~java
byte[] frame = {(byte) 0xFF, 0x00, 0x7F};
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.writeBytes(frame);
~~~

Dữ liệu chứa đúng ba byte **`FF 00 7F`**. Khi biểu diễn dưới kiểu `byte` Java, `(byte)0xFF` có giá trị signed là -1, nhưng các bit được lưu vẫn là `0xFF`. Đừng dùng `toString()` như một hex dump cho dữ liệu tùy ý.

### Nếu dữ liệu là văn bản

Chọn charset rõ ràng, ví dụ UTF-8:

~~~java
String text = "Xin chào";
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.writeBytes(payload);
String restored = out.toString(StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa cần import `StandardCharsets` và `ByteArrayOutputStream`; hai biến `text` và `restored` có nội dung ký tự giống nhau.

**Điểm cần nhớ:** `String.length()` đếm UTF-16 code units; `payload.length` đếm byte của biểu diễn UTF-8. Với tiếng Việt, emoji hoặc các ký tự ngoài ASCII, hai số này **không nhất thiết bằng nhau**. Một lời gọi `write(payload,off,len)` cần tính `off`/`len` theo **byte indices**; nếu cắt ngay giữa một ký tự UTF-8 nhiều byte, việc giải mã lát cắt có thể tạo ký tự thay thế hoặc báo lỗi tùy decoder.

**Không nhầm với `DataOutputStream.writeBytes(String)`:** tên gần giống nhưng đó là method khác, nhận **String** và lấy phần thấp của mỗi `char`, **không mã hóa văn bản theo UTF-8**. Với dữ liệu Unicode mới, đừng dùng phương thức đó như một lối tắt thay `text.getBytes(StandardCharsets.UTF_8)`. Dùng `ByteArrayOutputStream.writeBytes(byte[])` với kết quả mã hóa UTF-8 là đường đi rõ ràng.

## 10. Copy, kích thước và chi phí bộ nhớ

Một `ByteArrayOutputStream` duy trì buffer nội bộ và số byte hiện hợp lệ:

- `size()` trả số byte đã tích lũy.
- `writeBytes(b)` và `write(b,off,len)` **nối byte** và tăng size theo số byte ghi.
- Khi sức chứa không đủ, buffer nội bộ có thể được **mở rộng**, có chi phí cấp phát/copy.
- `toByteArray()` tạo **một mảng byte mới** chứa bản sao dữ liệu hiện có, không trả view trực tiếp của buffer nội bộ.
- `reset()` đưa số byte hợp lệ về 0, cho phép tái sử dụng buffer; không làm đổi các bản sao trước đó đã trả ra bởi `toByteArray()`.
- `close()` của **ByteArrayOutputStream** không có hiệu ứng làm stream mất khả năng ghi; đây là đặc thù của class in-memory, **không** áp dụng chung cho file/network streams.

### Không đồng nhất “tiện dụng” với “zero-copy”

`writeBytes(b)` là cách viết gọn cho full-range write. Nó không tạo ra một view trực tiếp đến mảng `b` và không bảo đảm zero-copy. Ví dụ phần 4 đã chứng minh thay `source[0]` sau khi ghi không làm dữ liệu đã lưu trong BAOS đổi.

Trong ứng dụng xử lý payload lớn, cần cân nhắc:

1. Nếu đã có mảng cần ghi toàn bộ, dùng `writeBytes(b)` trực tiếp.
2. Nếu chỉ cần một phần, dùng `write(b,off,len)` để **tránh tạo mảng con tạm thời** bằng `Arrays.copyOfRange(...)`.
3. Nếu cần biết dung lượng ước tính, có thể tạo `new ByteArrayOutputStream(initialCapacity)` với kích thước hợp lý để giảm số lần nới buffer.
4. Đừng giữ nhiều bản sao không cần thiết: `toByteArray()` tạo bản sao; kết hợp nhiều byte arrays cỡ lớn có thể làm tăng bộ nhớ dùng tạm.
5. Đừng đưa trực tiếp nội dung nhị phân chưa xác định charset vào log dạng text.
6. Nếu payload rất lớn hoặc có thể stream thẳng sang file/network, cân nhắc dùng `OutputStream` phù hợp thay vì gom mọi thứ vào một `ByteArrayOutputStream` rồi mới ghi ra ngoài.

Không có bằng chứng tổng quát rằng `writeBytes(b)` luôn nhanh hơn `write(b,0,b.length)`. Hai câu lệnh có hợp đồng tương đương và thường đi qua cùng logic ghi trong BAOS; nếu performance là yêu cầu, đo workload cụ thể bằng benchmark đáng tin, tránh microbenchmark không đủ warmup.

## 11. Tình huống thực tế: ghép header và payload

Giả sử gói dữ liệu đơn giản có:

~~~text
[1 byte version][2 byte flags][N byte payload]
~~~

Bạn có thể ghi header riêng và chép payload theo lát cắt:

~~~java
byte[] packet = new byte[] {
        0x01, 0x11, 0x22, 0x41, 0x42, 0x43, 0x44
};
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.write(packet, 0, 3); // version + flags
out.write(packet, 3, 4); // payload ABCD
~~~

Đây là **mã minh họa**; byte cuối cùng lần lượt tạo ra dữ liệu hex `01 11 22 41 42 43 44`. Nếu đã có **toàn bộ packet** trong mảng, một câu `out.writeBytes(packet)` cũng tạo đúng output như hai lệnh lát cắt, nhưng có thể **kém rõ ràng hơn** khi cần xử lý riêng header/payload hoặc khi dữ liệu đầu vào chứa phần dư không được gửi.

Một thiết kế điển hình hơn khi payload chứa dữ liệu không cần ghi hết:

~~~java
byte[] receiveBuffer = new byte[4096];
int bytesReceived = 120;          // Giả định đã đọc đúng 120 byte có hiệu lực.
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.write(receiveBuffer, 0, bytesReceived);
~~~

Nếu gọi `writeBytes(receiveBuffer)` trong tình huống này, bạn sẽ ghi **toàn bộ 4096 byte**, gồm cả phần buffer chưa được reader điền dữ liệu có hiệu lực. Đó là lỗi logic đặc biệt dễ xuất hiện khi làm việc với socket, protocol binary hoặc kết quả đọc từ `InputStream.read(byte[])`.

**Quy tắc thực tế:** chọn `writeBytes` chỉ khi **toàn bộ mảng là payload**. Nếu một mảng có **capacity lớn hơn số byte hợp lệ**, phải dùng `write(b,off,len)` với `len` là số byte thực sự có dữ liệu. Đây là khác biệt quan trọng hơn việc nhớ tên method.

## 12. Những lỗi thường gặp và cách sửa

**Lỗi 1 — “`writeBytes(b)` ghi một phần b khi chỉ có vài byte hợp lệ.”**  
Sai. Nó ghi toàn bộ `b.length` byte; dùng `write(b,0,bytesValid)` khi bộ đệm nhận có vùng dư.

**Lỗi 2 — “`write(b,2,5)` ghi từ index 2 đến index 5.”**  
Sai. Nó ghi **5 byte bắt đầu tại index 2**, tức khoảng [2,7), nếu đủ dài. Nếu muốn [2,5), truyền `len=3`.

**Lỗi 3 — “off là vị trí ghi đè trong ByteArrayOutputStream.”**  
Sai. `off` là vị trí đầu trong **mảng nguồn**. BAOS **nối** dữ liệu vào cuối.

**Lỗi 4 — “Có thể dùng `out.writeBytes(b)` với mọi `OutputStream`.”**  
Sai. `writeBytes(byte[])` là method **của `ByteArrayOutputStream`**, không thuộc API chuẩn `OutputStream`.

**Lỗi 5 — “`writeBytes(null)` tương đương ghi mảng trống.”**  
Sai. `null` gây `NullPointerException`; muốn không ghi byte thì truyền `new byte[0]` hoặc bỏ qua thao tác có chủ đích.

**Lỗi 6 — “off=b.length, len=0 luôn sai.”**  
Sai. Đoạn trống ở cuối mảng hợp lệ và không thêm byte.

**Lỗi 7 — “writeBytes sẽ tự mã hóa String hoặc lấy UTF-8.”**  
Sai. Nó chỉ nhận `byte[]`; muốn mã hóa ký tự thì gọi `text.getBytes(StandardCharsets.UTF_8)` trước.

**Lỗi 8 — “writeBytes thêm một byte kết thúc bằng 0 như C string.”**  
Sai. Mọi byte trong mảng, kể cả `0x00`, đều được ghi như dữ liệu.

**Lỗi 9 — “Gọi cả writeBytes(b) và write(b,0,b.length) sẽ không bị trùng.”**  
Sai. Hai lần gọi trên cùng stream **nối hai lần** cùng dữ liệu.

**Lỗi 10 — “ByteArrayOutputStream giữ tham chiếu đến mảng nguồn, nên sửa b sẽ đổi output cũ.”**  
Sai. BAOS chép các byte. Ví dụ phần 4 kiểm tra rõ nội dung cũ không đổi.

**Lỗi 11 — “writeBytes nhanh hơn vì nó không copy.”**  
Không đúng theo API. Convenience method không có cam kết zero-copy; so sánh hiệu suất cần đo, không suy từ tên.

**Lỗi 12 — “DataOutputStream.writeBytes(String) và ByteArrayOutputStream.writeBytes(byte[]) là cùng một API.”**  
Sai. Một bên nhận String và xử lý char theo quy tắc riêng, một bên nhận byte[] đã được mã hóa/chọn sẵn.

**Lỗi 13 — “Cả hai method đều ném checked IOException như FileOutputStream.write.”**  
Không đối với chữ ký trực tiếp của `ByteArrayOutputStream.writeBytes` và `ByteArrayOutputStream.write(b,off,len)`. Tuy nhiên chữ ký `OutputStream.write(...)` **có** `IOException`; compiler xét kiểu tĩnh.

**Lỗi 14 — “toByteArray() trả thẳng buffer nội bộ để tránh copy.”**  
Sai. Method trả mảng mới chứa bản sao các byte có hiệu lực.

**Lỗi 15 — “Khi BAOS đã ghi payload, phải gọi reset() trước mỗi lần ghi tiếp.”**  
Không bắt buộc; chỉ gọi `reset()` khi **muốn bỏ dữ liệu hiện tại** và bắt đầu tích lũy lại. Nếu muốn nối thêm, không reset.

**Lỗi 16 — “ByteArrayOutputStream.writeBytes là API của riêng Java 14.”**  
Sai. Nó có **since Java 11** và tiếp tục tồn tại trong Java 14/17/26. Chỉ sử dụng nó khi target Java ít nhất 11; trong bài ví dụ chạy Java 17+.

## 13. Checklist chọn đúng overload

Trước khi ghi byte vào BAOS, tự trả lời:

1. **Biến của tôi có kiểu gì?** `ByteArrayOutputStream` hay `OutputStream` chung?
2. **Mảng `b` chứa bao nhiêu byte hợp lệ?** Đã điền đủ `b.length` hay mới `bytesRead` byte?
3. **Cần toàn bộ hay một đoạn?** Toàn bộ → `writeBytes(b)`; đoạn → `write(b,off,len)`.
4. **Có nguy cơ `null` không?** Cả hai đường đều yêu cầu array khác null.
5. **off/len tính bằng byte chưa?** Không dùng số ký tự UTF-16 thay cho số byte UTF-8.
6. **Có đang nối dữ liệu không mong muốn?** Mỗi lần write đều appends; nếu cần ghi mới từ đầu, chủ động tạo stream mới hoặc `reset()`.
7. **Có cần chuyển kết quả ra ngoài?** `toByteArray()` lấy copy; `writeTo(out)` chuyển nội dung BAOS sang một stream đích.
8. **Có phù hợp với kích thước dữ liệu?** BAOS giữ byte trong RAM; cân nhắc stream sang file/network nếu payload rất lớn.
9. **Có byte nhị phân không thể hiển thị dưới text?** Để QA, so sánh `byte[]` bằng `Arrays.equals` hoặc xem hex thay vì ép `toString()` không có charset.
10. **Đã có test cho off/len=0, null và out-of-bounds?** Các ranh giới này giúp tránh lỗi khi buffer nhận bị tái sử dụng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `ByteArrayOutputStream.writeBytes(b)` có quan hệ gì với `write(b,0,b.length)`?  
**Đáp án:** Hai cách tương đương về hành vi ghi toàn bộ array, theo Javadoc của ByteArrayOutputStream.

**Câu 2.** Với byte array `{10,20,30,40}`, `write(b,1,2)` ghi gì?  
**Đáp án:** Hai byte **20,30** (index 1 và 2).

**Câu 3.** `write(b,1,2)` có ghi đè hai byte trong stream từ offset 1 không?  
**Đáp án:** Không. Offset chỉ vị trí **mảng nguồn**; bytes được nối vào cuối stream.

**Câu 4.** Mảng dài 4096 nhưng chỉ nhận 120 byte, nên dùng gì?  
**Đáp án:** `write(b,0,120)`. `writeBytes(b)` sẽ ghi cả 4096 byte.

**Câu 5.** Gọi `write(b,b.length,0)` hợp lệ không?  
**Đáp án:** Có, ghi 0 byte.

**Câu 6.** Gọi `writeBytes(null)` có làm stream giữ nguyên không?  
**Đáp án:** Nó ném `NullPointerException`; không phải lệnh ghi trống hợp lệ.

**Câu 7.** Gọi `write(b,3,2)` khi `b.length=4` có hợp lệ không?  
**Đáp án:** Không, vì cần index 3 và 4 nhưng mảng chỉ có đến 3; ném `IndexOutOfBoundsException`.

**Câu 8.** Vì sao `OutputStream s = new ByteArrayOutputStream(); s.writeBytes(b);` không biên dịch?  
**Đáp án:** Kiểu tĩnh `OutputStream` không khai báo method `writeBytes(byte[])`. Dùng `s.write(b)` hoặc ba tham số.

**Câu 9.** Có nên dùng `writeBytes(text.getBytes())` không nêu charset trong giao thức cần tính nhất quán?  
**Đáp án:** Không nên. Dùng `text.getBytes(StandardCharsets.UTF_8)` để xác định encoding tường minh.

**Câu 10.** `toByteArray()` có tạo bản sao không?  
**Đáp án:** Có. Nó tạo mảng byte mới chứa các byte đã tích lũy.

**Câu 11.** `writeBytes` có đảm bảo tốc độ cao hơn `write(b,0,b.length)` không?  
**Đáp án:** Không. Đây là convenience method cùng hợp đồng ghi toàn bộ, không có bảo đảm hiệu năng tốt hơn.

**Câu 12.** Khi nào `writeTo(OutputStream)` phù hợp hơn `writeBytes(byte[])`?  
**Đáp án:** Khi đã có dữ liệu **trong BAOS** và muốn chuyển sang một stream **đích**. `writeBytes` lại nhận mảng byte từ bên ngoài để thêm vào BAOS.

## Tài liệu chính thức

- **Oracle Java SE 14 — ByteArrayOutputStream:** `writeBytes(byte[])` có từ Java 11 và tương đương `write(b,0,b.length)`; `write(b,off,len)` kiểm tra offset/length, `reset`, `toByteArray` và `writeTo`: https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/io/ByteArrayOutputStream.html
- **Oracle Java SE 17 — ByteArrayOutputStream:** cùng hợp đồng đang được hỗ trợ ở Java 17+, bao gồm `writeBytes`, `write` và `toString(Charset)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html
- **Oracle Java SE 26 — ByteArrayOutputStream:** API Note vẫn nêu tương đương, minh chứng method còn áp dụng trong bản Java hiện đại: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ByteArrayOutputStream.html
- **Oracle Java SE 17 — OutputStream:** các overload `write(byte[])` / `write(byte[],off,len)` và hợp đồng tương đương khi ghi cả mảng; phân biệt checked `IOException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html
- **Oracle Java SE 17 — StandardCharsets:** định nghĩa UTF-8 dùng trong ví dụ, tránh phụ thuộc default charset của môi trường: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html
- **Oracle Java SE 17 — HexFormat:** trình bày byte nhị phân ở dạng hex một cách chính xác: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- **Oracle Java SE 17 — DataOutputStream:** phân biệt `writeBytes(String)` với `ByteArrayOutputStream.writeBytes(byte[])`, tránh lỗi mã hóa văn bản Unicode: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html