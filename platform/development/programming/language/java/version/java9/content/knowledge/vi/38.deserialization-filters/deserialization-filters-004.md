# Giới hạn tổng byte qua `ObjectInputFilter.FilterInfo`

`ObjectInputFilter` được giới thiệu trong Java 9 để kiểm soát dữ liệu khi `ObjectInputStream` giải tuần tự object. `ObjectInputFilter.FilterInfo` cung cấp thông tin về object đang được đọc và trạng thái của luồng, trong đó `streamBytes()` trả về số byte đã được tiêu thụ từ luồng tại thời điểm filter được gọi.

Nhờ `streamBytes()`, filter có thể từ chối một object graph khi số byte đã đọc vượt ngân sách cho phép. Tuy nhiên, đây là bộ đếm tại các điểm gọi filter trong quá trình giải tuần tự, không phải bộ giới hạn byte thô bao quanh mọi thao tác đọc. Nếu cần bảo đảm tuyệt đối rằng không đọc quá N byte từ nguồn, hãy kết hợp filter với một input stream có hạn mức byte.

## 1. `ObjectInputFilter` và `FilterInfo`

`ObjectInputFilter` là callback mà `ObjectInputStream` sử dụng để quyết định một object hoặc array có được phép giải tuần tự hay không. Có thể cài filter riêng cho một stream bằng `ObjectInputStream.setObjectInputFilter(...)`, hoặc cấu hình filter ở cấp JVM theo chính sách triển khai.

`FilterInfo` cung cấp năm thông tin chính:

| Phương thức | Ý nghĩa |
| --- | --- |
| `serialClass()` | Lớp của object hoặc array đang được kiểm tra; có thể là `null` ở một số callback, chẳng hạn callback liên quan đến tham chiếu đã đọc. |
| `arrayLength()` | Số phần tử của array đang được kiểm tra; trả `-1` nếu callback không dành cho array. |
| `depth()` | Độ sâu hiện tại của đồ thị object đang được giải tuần tự. |
| `references()` | Số tham chiếu object đã được đọc trong stream đến thời điểm đó. |
| `streamBytes()` | Tổng số byte đã tiêu thụ từ stream đến thời điểm filter được gọi. |

`streamBytes()` là số tích lũy từ đầu stream, bao gồm dữ liệu serialization đã đọc trước callback hiện tại. Nó không phải kích thước file, không phải kích thước object hiện tại và không dự đoán số byte còn lại.

## 2. Đọc `streamBytes()` để đặt ngân sách byte

Ví dụ filter đơn giản:

```java
private static final long MAX_STREAM_BYTES = 1_048_576;

ObjectInputFilter byteLimitFilter = info -> {
    if (info.streamBytes() > MAX_STREAM_BYTES) {
        return ObjectInputFilter.Status.REJECTED;
    }
    return ObjectInputFilter.Status.UNDECIDED;
};
```

Khi số byte đã đọc vượt 1 MiB, filter trả `REJECTED`. `ObjectInputStream` sẽ từ chối quá trình giải tuần tự và thường ném `InvalidClassException` với thông tin filter đã reject.

Dùng phép so sánh `>` nếu cho phép stream có đúng bằng ngân sách. Nếu chính sách yêu cầu từ chối ngay khi đạt ngưỡng, hãy định nghĩa rõ ngưỡng nghiệp vụ và dùng phép so sánh tương ứng; nhớ rằng giá trị chỉ được quan sát tại callback.

### Ý nghĩa ba trạng thái

- `ALLOWED`: filter cho phép đối tượng tại callback hiện tại.
- `REJECTED`: từ chối đối tượng; quá trình giải tuần tự bị dừng.
- `UNDECIDED`: filter chưa đưa ra quyết định. Trạng thái này phù hợp khi byte count và các giới hạn khác vẫn trong ngưỡng, để những quy tắc filter khác có cơ hội quyết định.

Trong filter kết hợp nhiều điều kiện, nên trả `REJECTED` ngay khi một giới hạn bị vi phạm và trả `UNDECIDED` khi callback hiện tại chưa có lý do để từ chối.

## 3. Cài filter trước khi đọc object

Cài filter trên `ObjectInputStream` trước lần gọi `readObject()` đầu tiên:

```java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(byteLimitFilter);
    Object value = input.readObject();
}
```

Đặt filter sớm để các object đầu tiên cũng chịu chính sách kiểm tra. Không chờ đọc xong một phần dữ liệu rồi mới cài filter.

Filter theo stream chỉ áp dụng cho stream đó. Với ứng dụng nhận dữ liệu serialization từ nhiều nguồn, hãy bảo đảm mọi `ObjectInputStream` đều được cấu hình chính sách phù hợp; không giả định rằng cài filter cho một stream sẽ tự bảo vệ các stream khác.

## 4. Kết hợp giới hạn byte với các thuộc tính khác

Không nên chỉ giới hạn byte. Một object graph nhỏ về số byte vẫn có thể quá sâu, có quá nhiều tham chiếu hoặc yêu cầu tạo array lớn. Filter có thể kiểm tra đồng thời:

```java
private static final long MAX_BYTES = 1_048_576;
private static final long MAX_DEPTH = 32;
private static final long MAX_REFERENCES = 10_000;
private static final long MAX_ARRAY_LENGTH = 65_536;

ObjectInputFilter filter = info -> {
    if (info.streamBytes() > MAX_BYTES
            || info.depth() > MAX_DEPTH
            || info.references() > MAX_REFERENCES
            || info.arrayLength() > MAX_ARRAY_LENGTH) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type != null && !isAllowedType(type)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

`arrayLength()` là `-1` khi callback không liên quan đến array, nên điều kiện `arrayLength() > MAX_ARRAY_LENGTH` không từ chối nhầm callback thông thường. `serialClass()` cũng cần kiểm tra null trước khi so sánh hoặc đọc tên lớp.

`isAllowedType` trong đoạn trên là chính sách allowlist do ứng dụng định nghĩa. Trong ứng dụng thật, hãy liệt kê chính xác DTO và kiểu dữ liệu cần thiết thay vì cho phép mọi lớp trong classpath.

## 5. Filter pattern có sẵn với `maxbytes`

Java cung cấp filter pattern để khai báo các giới hạn phổ biến mà không cần tự viết toàn bộ callback:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
    "maxbytes=1048576;maxdepth=32;maxrefs=10000;maxarray=65536");
```

Các thuộc tính hữu ích:

| Thuộc tính | Giới hạn |
| --- | --- |
| `maxbytes` | Số byte stream đã tiêu thụ tại các điểm kiểm tra filter. |
| `maxdepth` | Độ sâu đồ thị object. |
| `maxrefs` | Số tham chiếu object. |
| `maxarray` | Độ dài array. |

Filter pattern có thể kết hợp với các mẫu tên lớp/package để giới hạn kiểu được phép. Khi cần chính sách động hoặc ghi log lý do từ chối, custom filter với `FilterInfo` linh hoạt hơn.

`maxbytes` vẫn là một giới hạn thuộc cơ chế serialization filter. Nó được đánh giá khi filter được gọi; không thay thế giới hạn số byte mà tầng `InputStream` có thể đọc từ socket, file hoặc nguồn dữ liệu bên dưới.

## 6. Giới hạn quan trọng: filter không chạy cho từng byte

Không được hiểu `streamBytes()` là bộ đếm được kiểm tra sau mỗi byte đọc. Filter được gọi tại các điểm kiểm tra trong quá trình giải tuần tự object/array và tham chiếu; các byte primitive hoặc nội dung payload có thể được đọc giữa hai lần callback.

Ví dụ, khi giải tuần tự một object có field `byte[]` lớn:

1. Filter có thể được gọi để kiểm tra object bao ngoài.
2. Filter được gọi để kiểm tra array và biết `arrayLength()`.
3. Nội dung byte của array được đọc vào bộ nhớ sau callback kiểm tra array.
4. Nếu stream không có object tiếp theo, có thể không có callback khác để quan sát số byte đã tăng sau khi payload được đọc.

Vì vậy, một object duy nhất có payload lớn có thể vượt ngân sách byte giữa hai checkpoint. Lần callback kế tiếp có thể nhìn thấy `streamBytes()` đã vượt ngưỡng và từ chối object kế tiếp, nhưng object lớn trước đó đã được đọc xong.

Đây là lý do phải phân biệt **giới hạn tại checkpoint giải tuần tự** với **giới hạn cứng số byte đọc từ nguồn**.

## 7. Dùng input stream có hạn mức cho giới hạn byte cứng

Nếu yêu cầu là không cho `ObjectInputStream` nhận quá N byte từ nguồn, hãy đặt một wrapper có giới hạn ở bên dưới nó:

```text
File / socket / input source
          |
          v
LimitedInputStream (tối đa N byte)
          |
          v
ObjectInputStream
          |
          v
ObjectInputFilter (kiểu, depth, refs, streamBytes, arrayLength)
```

Wrapper cần giới hạn cả `read()`, `read(byte[], off, len)` và `skip()`. Nếu chỉ override một phương thức đọc, một đường đọc khác có thể vượt qua bộ đếm. Nếu hỗ trợ `mark/reset`, cần khôi phục bộ đếm đúng khi reset; ví dụ bên dưới chủ động tắt mark/reset để tránh làm sai ngân sách.

Khi wrapper đã cung cấp đủ N byte mà object còn cần đọc thêm, nó trả EOF. `ObjectInputStream` sẽ báo stream bị thiếu dữ liệu, thường bằng `EOFException`. Không byte nào vượt quá ngân sách được chuyển lên tầng giải tuần tự.

## 8. Chương trình Java 17 hoàn chỉnh

Ví dụ sau tạo một stream gồm hai object. Object đầu tiên chứa mảng 1.024 byte; object thứ hai nhỏ hơn. Custom filter có ngưỡng 128 byte. Do callback kiểm tra array xảy ra trước khi payload array được đọc, object lớn đầu tiên có thể hoàn tất; callback tiếp theo nhìn thấy tổng byte đã vượt ngưỡng và từ chối object thứ hai. Cùng dữ liệu đó được đọc lần nữa qua `LimitedInputStream` để chứng minh giới hạn cứng.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.util.Objects;

public class Main {
    private static final long FILTER_BYTE_LIMIT = 128;
    private static final long HARD_BYTE_LIMIT = 128;

    static final class Payload implements Serializable {
        private static final long serialVersionUID = 1L;
        final byte[] data;

        Payload(int size) {
            data = new byte[size];
        }
    }

    static final class LimitedInputStream extends FilterInputStream {
        private long remaining;

        LimitedInputStream(InputStream input, long limit) {
            super(input);
            if (limit < 0) {
                throw new IllegalArgumentException("limit must be non-negative");
            }
            remaining = limit;
        }

        @Override
        public int read() throws IOException {
            if (remaining == 0) {
                return -1;
            }
            int value = super.read();
            if (value != -1) {
                remaining--;
            }
            return value;
        }

        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            Objects.requireNonNull(buffer);
            Objects.checkFromIndexSize(offset, length, buffer.length);
            if (length == 0) {
                return 0;
            }
            if (remaining == 0) {
                return -1;
            }
            int allowed = (int) Math.min((long) length, remaining);
            int count = super.read(buffer, offset, allowed);
            if (count > 0) {
                remaining -= count;
            }
            return count;
        }

        @Override
        public long skip(long count) throws IOException {
            if (count <= 0 || remaining == 0) {
                return 0;
            }
            long skipped = super.skip(Math.min(count, remaining));
            remaining -= skipped;
            return skipped;
        }

        @Override
        public int available() throws IOException {
            return (int) Math.min((long) super.available(), remaining);
        }

        @Override
        public boolean markSupported() {
            return false;
        }

        @Override
        public synchronized void mark(int readLimit) {
        }

        @Override
        public synchronized void reset() throws IOException {
            throw new IOException("mark/reset is not supported");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] serialized = serializePayloads();
        System.out.println("serialized stream bytes: " + serialized.length);

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(serialized))) {
            input.setObjectInputFilter(info -> {
                if (info.streamBytes() > FILTER_BYTE_LIMIT
                        || info.depth() > 16
                        || info.references() > 1000
                        || info.arrayLength() > 4096) {
                    return ObjectInputFilter.Status.REJECTED;
                }

                Class<?> type = info.serialClass();
                if (type != null && type != Payload.class && type != byte[].class) {
                    return ObjectInputFilter.Status.REJECTED;
                }
                return ObjectInputFilter.Status.UNDECIDED;
            });

            input.readObject();
            System.out.println("large first object passed its filter checkpoints");

            try {
                input.readObject();
                throw new AssertionError("second object should be rejected");
            } catch (InvalidClassException expected) {
                System.out.println("next object rejected after byte budget: "
                    + expected.getMessage().contains("filter status: REJECTED"));
            }
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new LimitedInputStream(
                    new ByteArrayInputStream(serialized), HARD_BYTE_LIMIT))) {
            input.readObject();
            throw new AssertionError("hard byte limit should stop the large object");
        } catch (EOFException expected) {
            System.out.println("hard input limit stopped reading at "
                + HARD_BYTE_LIMIT + " bytes");
        }
    }

    private static byte[] serializePayloads() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(new Payload(1024));
            output.writeObject(new Payload(16));
        }
        return bytes.toByteArray();
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout chính xác:

```text
serialized stream bytes: 1124
large first object passed its filter checkpoints
next object rejected after byte budget: true
hard input limit stopped reading at 128 bytes
```

Trong ví dụ, `FILTER_BYTE_LIMIT` minh họa việc từ chối tại callback filter. `HARD_BYTE_LIMIT` giới hạn số byte mà wrapper chuyển cho `ObjectInputStream`, bao gồm cả serialization stream header. `LimitedInputStream` trả EOF khi hết ngân sách; nếu object chưa hoàn tất, quá trình đọc thất bại.

## 9. Chọn giới hạn phù hợp cho ứng dụng

Giới hạn byte nên xuất phát từ hợp đồng dữ liệu và tải thực tế:

- **Thông điệp nhỏ:** đặt ngân sách theo kích thước tối đa của payload hợp lệ, cộng phần overhead serialization có dự phòng.
- **Đồ thị object lớn:** kết hợp byte budget với depth, references và array length để hạn chế cấu trúc tiêu tốn CPU/bộ nhớ.
- **File upload:** kiểm tra kích thước file sớm nếu nguồn là file có kích thước xác định, nhưng vẫn đặt giới hạn ở input stream để kiểm soát số byte thực sự đọc.
- **Socket hoặc HTTP body:** giới hạn ở tầng stream khi đọc dữ liệu; không chỉ dựa vào `Content-Length` hoặc metadata do bên gửi cung cấp.
- **Nhiều object trong một stream:** nhớ rằng `streamBytes()` là bộ đếm tích lũy của cả stream, không tự đặt lại sau mỗi `readObject()`.

Không chọn ngưỡng quá thấp khiến dữ liệu hợp lệ bị từ chối, cũng không chọn ngưỡng quá cao làm mất tác dụng bảo vệ. Theo dõi kích thước payload thực tế và điều chỉnh chính sách dựa trên số liệu.

## 10. Những điều `streamBytes()` không thay thế

`streamBytes()` không thay thế các lớp bảo vệ khác:

1. **Allowlist kiểu:** giới hạn byte không ngăn mọi lớp không mong muốn được giải tuần tự nếu filter không kiểm tra `serialClass()`.
2. **Giới hạn array:** một array lớn có thể gây áp lực bộ nhớ; kiểm tra `arrayLength()` riêng.
3. **Giới hạn depth/references:** object graph sâu hoặc nhiều tham chiếu cần giới hạn riêng.
4. **Giới hạn byte thô:** dùng bounded input stream để không chuyển quá N byte từ nguồn.
5. **Kiểm tra nghiệp vụ:** sau khi giải tuần tự, vẫn phải xác thực dữ liệu, trạng thái và quyền của ứng dụng.
6. **Xác thực nguồn gửi:** filter không xác minh danh tính, chữ ký hoặc tính toàn vẹn của dữ liệu.

Serialization filter là một lớp phòng vệ khi đọc object graph; nó không biến dữ liệu serialization từ nguồn không tin cậy thành dữ liệu đáng tin cậy.

## 11. Lỗi thường gặp

1. **Nhầm `streamBytes()` với kích thước file.** Đây là số byte đã tiêu thụ tại thời điểm callback, không phải tổng độ dài đầu vào.
2. **Cho rằng filter được gọi sau mỗi byte.** Filter chạy tại các checkpoint giải tuần tự object/array; primitive payload có thể được đọc giữa các callback.
3. **Chỉ kiểm tra object đầu tiên.** Với stream chứa nhiều object, cần hiểu bộ đếm tích lũy và chính sách áp dụng cho toàn stream.
4. **Dùng `arrayLength()` thay cho `streamBytes()`.** Một trường là số phần tử của array, trường kia là số byte đã đọc.
5. **Không xử lý `serialClass()` null.** Callback không phải lúc nào cũng có class cụ thể; luôn kiểm tra null trước khi dùng.
6. **Trả `ALLOWED` quá sớm.** Điều này có thể làm mất cơ hội để filter khác đưa ra quyết định; dùng `UNDECIDED` khi filter hiện tại chưa từ chối.
7. **Chỉ giới hạn byte mà bỏ depth/references/array.** Các chiều tài nguyên khác vẫn có thể gây tải lớn.
8. **Cài filter sau `readObject()`.** Object đầu tiên đã được đọc trước khi chính sách được cài.
9. **Chỉ dùng filter để giới hạn socket/file body.** Đặt bounded input stream bên dưới `ObjectInputStream` khi cần giới hạn byte thực đọc.
10. **Wrapper chỉ override `read()`.** `ObjectInputStream` có thể đọc theo mảng hoặc skip; phải giới hạn mọi đường đọc.
11. **Cho phép mark/reset mà không khôi phục bộ đếm.** Reset có thể làm bộ đếm sai; ví dụ giới hạn tắt mark/reset.
12. **Dựa vào `System.gc()` hoặc filter để quản lý tài nguyên.** Đây là hai cơ chế không liên quan đến việc giới hạn byte đầu vào.

## 12. Ghi nhớ

1. `FilterInfo.streamBytes()` trả số byte đã tiêu thụ từ stream tại thời điểm filter được gọi.
2. `streamBytes()` là bộ đếm tích lũy, không phải kích thước cuối cùng của file hoặc object.
3. Trả `REJECTED` khi vượt ngân sách sẽ làm `ObjectInputStream` từ chối object, thường bằng `InvalidClassException`.
4. Có thể kết hợp byte limit với `depth()`, `references()`, `arrayLength()` và allowlist qua `serialClass()`.
5. Filter pattern hỗ trợ `maxbytes`, `maxdepth`, `maxrefs` và `maxarray`.
6. Filter không chạy cho từng byte; payload lớn có thể được đọc giữa hai checkpoint.
7. Khi cần giới hạn cứng số byte nguồn cung cấp, đặt bounded input stream bên dưới `ObjectInputStream`.
8. Cài filter trước lần đọc object đầu tiên và áp dụng chính sách cho mọi stream nhận dữ liệu serialization.