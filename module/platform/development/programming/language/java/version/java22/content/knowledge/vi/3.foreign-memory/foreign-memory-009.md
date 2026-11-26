# Cắt lát, sao chép, điền dữ liệu và chuyển đổi giữa MemorySegment, mảng và ByteBuffer

Foreign Function & Memory API (FFM API) cung cấp cách làm việc có kiểm soát với vùng nhớ trong Java heap và ngoài heap. Thành phần trung tâm là @@BT@@MemorySegment@@BT@@: một đối tượng mô tả một vùng nhớ liên tục, có giới hạn kích thước, thời gian tồn tại và quyền truy cập.

Trong Java 22, FFM API được hoàn thiện theo JEP 454 và nằm trong package @@BT@@java.lang.foreign@@BT@@. Bài này tập trung vào các thao tác thường gặp khi xử lý dữ liệu: tạo lát cắt, sao chép, điền giá trị, và trao đổi dữ liệu với mảng primitive hoặc @@BT@@ByteBuffer@@BT@@. Các ví dụ dùng API chuẩn đã ổn định từ Java 22.

## 1. Phân biệt view và copy

Trước khi chọn phương thức, cần xác định thao tác có tạo vùng dữ liệu độc lập hay chỉ tạo một góc nhìn khác trên cùng vùng nhớ.

| Thao tác | Phương thức tiêu biểu | Vùng dữ liệu | Có sao chép byte không? |
|---|---|---|---|
| Tạo lát cắt | @@BT@@asSlice(...)@@BT@@ | Chia sẻ vùng nhớ của segment gốc | Không |
| Bọc mảng primitive | @@BT@@MemorySegment.ofArray(array)@@BT@@ | Chia sẻ vùng nhớ của mảng | Không |
| Bọc @@BT@@ByteBuffer@@BT@@ | @@BT@@MemorySegment.ofBuffer(buffer)@@BT@@ | Chia sẻ vùng nhớ của buffer | Không |
| Tạo @@BT@@ByteBuffer@@BT@@ từ segment | @@BT@@segment.asByteBuffer()@@BT@@ | Chia sẻ vùng nhớ của segment | Không |
| Sao chép | @@BT@@MemorySegment.copy(...)@@BT@@, @@BT@@copyFrom(...)@@BT@@ | Ghi dữ liệu sang vùng đích | Có |
| Tạo mảng mới | @@BT@@segment.toArray(layout)@@BT@@ | Mảng độc lập | Có |
| Điền byte | @@BT@@segment.fill(value)@@BT@@ | Thay đổi chính segment hiện tại | Không tạo bản sao |

Một *view* cho phép nhiều đối tượng cùng truy cập một vùng dữ liệu. Vì vậy, ghi qua view có thể được nhìn thấy từ đối tượng gốc. Một thao tác *copy* tạo dữ liệu ở vùng đích; thay đổi vùng nguồn sau đó không tự cập nhật bản sao.

Phân biệt hai loại thao tác này giúp tránh sao chép không cần thiết và tránh nhầm rằng một view là bản sao độc lập.

## 2. Cắt lát MemorySegment bằng asSlice

@@BT@@asSlice(offset, size)@@BT@@ tạo một @@BT@@MemorySegment@@BT@@ mới mô tả một phần của vùng nhớ gốc. @@BT@@offset@@BT@@ và @@BT@@size@@BT@@ đều tính bằng byte.

Ví dụ, chia một vùng nhớ 64 byte thành phần header 16 byte và phần payload 48 byte:

@@BT@@@@BT@@@@BT@@java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment packet = arena.allocate(64, ValueLayout.JAVA_INT.byteAlignment());

    MemorySegment header = packet.asSlice(0, 16, ValueLayout.JAVA_INT.byteAlignment());
    MemorySegment payload = packet.asSlice(16, 48, ValueLayout.JAVA_INT.byteAlignment());

    header.set(ValueLayout.JAVA_INT, 0, 0x5041434B);
    payload.fill((byte) 0);
}
@@BT@@@@BT@@@@BT@@

@@BT@@header@@BT@@ và @@BT@@payload@@BT@@ dùng chung vùng nhớ với @@BT@@packet@@BT@@. Ghi vào một lát cắt cũng thay đổi vùng nhớ tương ứng trong segment gốc. @@BT@@asSlice@@BT@@ không cấp phát một vùng nhớ dữ liệu mới và không sao chép nội dung.

Lát cắt có các giới hạn chặt hơn segment gốc:

- Chỉ truy cập được các byte nằm trong khoảng của lát cắt. Truy cập vượt giới hạn sẽ bị từ chối.
- Lát cắt kế thừa scope và thời gian tồn tại của segment gốc. Khi @@BT@@Arena@@BT@@ quản lý vùng nhớ bị đóng, lát cắt cũng không còn truy cập được.
- Nếu segment gốc là read-only, lát cắt cũng read-only.
- Overload @@BT@@asSlice(offset, size)@@BT@@ tương đương với việc đặt alignment của lát cắt là 1 byte. Nếu cần đọc/ghi giá trị có alignment lớn hơn, hãy dùng @@BT@@asSlice(offset, size, byteAlignment)@@BT@@ hoặc @@BT@@asSlice(offset, layout)@@BT@@ và bảo đảm offset phù hợp.
- Các thao tác đọc/ghi vẫn phải tuân thủ yêu cầu alignment của @@BT@@ValueLayout@@BT@@.

Ngoài dạng truyền offset và kích thước, có thể dùng @@BT@@asSlice(offset)@@BT@@ để lấy phần còn lại từ offset đến cuối segment, hoặc @@BT@@asSlice(offset, layout)@@BT@@ để tạo lát cắt có kích thước và alignment theo một @@BT@@MemoryLayout@@BT@@.

Ví dụ khi làm việc với mảng phần tử @@BT@@int@@BT@@, offset phải đổi từ chỉ số phần tử sang byte:

@@BT@@@@BT@@@@BT@@java
long intSize = ValueLayout.JAVA_INT.byteSize();
MemorySegment thirdAndFourth = segment.asSlice(
    2 * intSize, 2 * intSize, ValueLayout.JAVA_INT.byteAlignment()
);
@@BT@@@@BT@@@@BT@@

Ở đây lát cắt bắt đầu tại byte thứ 8 và dài 8 byte nếu @@BT@@JAVA_INT@@BT@@ có kích thước 4 byte. @@BT@@asSlice@@BT@@ nhận offset theo byte, không nhận chỉ số phần tử.

## 3. Sao chép dữ liệu giữa các MemorySegment

@@BT@@MemorySegment.copy(...)@@BT@@ là phương thức static dùng để sao chép dữ liệu giữa hai segment. Overload đơn giản nhất nhận offset và số byte:

@@BT@@@@BT@@@@BT@@java
MemorySegment.copy(
    source, sourceOffset,
    destination, destinationOffset,
    byteCount
);
@@BT@@@@BT@@@@BT@@

Phương thức sao chép chính xác các byte trong vùng nguồn sang vùng đích. Nó không diễn giải dữ liệu thành @@BT@@int@@BT@@, @@BT@@long@@BT@@ hay kiểu phần tử khác. Đây là lựa chọn phù hợp khi cần sao chép một khối byte nguyên trạng.

Nếu đích là segment cần nhận toàn bộ nội dung của segment nguồn từ offset 0, có thể dùng @@BT@@destination.copyFrom(source)@@BT@@. Segment đích phải đủ lớn; dữ liệu được ghi từ đầu segment đích.

### Sao chép theo phần tử và byte order

Khi dữ liệu gồm các phần tử có kiểu, overload nhận @@BT@@ValueLayout@@BT@@ giúp mô tả cách diễn giải dữ liệu nguồn và đích:

@@BT@@@@BT@@@@BT@@java
MemorySegment.copy(
    source, ValueLayout.JAVA_INT, 0,
    destination, ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN), 0,
    elementCount
);
@@BT@@@@BT@@@@BT@@

Hai layout phải có cùng kích thước phần tử. Nếu byte order của chúng khác nhau, API hoán đổi byte tương ứng cho từng phần tử trong lúc sao chép. Đây là điểm khác với overload chỉ nhận số byte: overload raw-byte giữ nguyên chuỗi byte, không tự chuyển đổi cách biểu diễn số.

Khi sao chép các segment có vùng nhớ chồng lấn, API xử lý như thể vùng nguồn được chép tạm trước rồi mới ghi vào đích. Tuy vậy, vẫn cần bảo đảm offset và số byte nằm trong giới hạn của cả hai segment, segment còn sống và có thể truy cập từ thread hiện tại, đồng thời segment đích không ở chế độ read-only.

## 4. Điền dữ liệu bằng fill

@@BT@@fill(byte value)@@BT@@ ghi cùng một byte vào mọi vị trí trong segment:

@@BT@@@@BT@@@@BT@@java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment buffer = arena.allocate(32);

    buffer.fill((byte) 0);       // Đặt toàn bộ byte về 0.
    buffer.asSlice(8, 8).fill((byte) 0x7F);
}
@@BT@@@@BT@@@@BT@@

Sau thao tác trên:

- 8 byte đầu tiên có giá trị 0.
- 8 byte tiếp theo có giá trị @@BT@@0x7F@@BT@@.
- 16 byte cuối cùng có giá trị 0.

@@BT@@fill@@BT@@ lặp một mẫu byte trên toàn vùng nhớ, không điền một giá trị có kiểu vào từng phần tử. Ví dụ @@BT@@fill((byte) 1)@@BT@@ khiến mọi byte đều bằng 1; nó không có nghĩa là mọi @@BT@@int@@BT@@ trong vùng nhớ nhận giá trị số 1.

Phương thức này hữu ích để khởi tạo vùng nhớ về 0, đặt một mẫu byte kiểm tra hoặc đưa vùng nhớ về trạng thái xác định trước khi tái sử dụng. Không thể gọi @@BT@@fill@@BT@@ trên segment read-only. Segment cũng phải còn sống và thread gọi phải có quyền truy cập.

## 5. Chuyển đổi giữa MemorySegment và mảng primitive

FFM API hỗ trợ hai cách trao đổi dữ liệu với mảng: tạo view dùng chung bộ nhớ hoặc sao chép dữ liệu.

### Tạo heap segment dùng chung mảng

@@BT@@MemorySegment.ofArray(array)@@BT@@ tạo heap segment được hỗ trợ bởi chính mảng primitive truyền vào. Không có bản sao dữ liệu:

@@BT@@@@BT@@@@BT@@java
int[] values = {10, 20, 30, 40};

MemorySegment view = MemorySegment.ofArray(values);
view.set(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT.byteSize(), 99);

System.out.println(values[1]); // 99
@@BT@@@@BT@@@@BT@@

Thay đổi ở @@BT@@view@@BT@@ được nhìn thấy trong mảng @@BT@@values@@BT@@, vì cả hai cùng truy cập vùng dữ liệu. Ngược lại, nếu thay đổi @@BT@@values[1]@@BT@@, đọc qua segment cũng nhận được giá trị mới.

Các overload @@BT@@ofArray@@BT@@ có sẵn cho @@BT@@byte[]@@BT@@, @@BT@@char[]@@BT@@, @@BT@@short[]@@BT@@, @@BT@@int[]@@BT@@, @@BT@@float[]@@BT@@, @@BT@@long[]@@BT@@ và @@BT@@double[]@@BT@@. Đây là heap segment; dữ liệu vẫn nằm trong Java heap và được quản lý theo vòng đời của mảng.

### Sao chép từ mảng vào segment và ngược lại

Khi cần dữ liệu độc lập trong native memory, hãy cấp phát segment bằng @@BT@@Arena@@BT@@ rồi dùng @@BT@@MemorySegment.copy@@BT@@:

@@BT@@@@BT@@@@BT@@java
int[] source = {10, 20, 30, 40};

try (Arena arena = Arena.ofConfined()) {
    long byteSize = (long) source.length * ValueLayout.JAVA_INT.byteSize();

    MemorySegment nativeData = arena.allocate(
        byteSize,
        ValueLayout.JAVA_INT.byteAlignment()
    );

    // Sao chép toàn bộ mảng vào native segment.
    MemorySegment.copy(
        source, 0,
        nativeData, ValueLayout.JAVA_INT, 0,
        source.length
    );

    // Chỉnh sửa bản dữ liệu trong native memory.
    nativeData.set(ValueLayout.JAVA_INT, 0, 99);

    // Tạo một mảng Java mới từ segment.
    int[] result = nativeData.toArray(ValueLayout.JAVA_INT);
    System.out.println(result[0]); // 99
    System.out.println(source[0]); // 10
}
@@BT@@@@BT@@@@BT@@

@@BT@@MemorySegment.copy(array, ...)@@BT@@ nhận chỉ số bắt đầu trong mảng, layout phần tử ở đích, offset đích tính bằng byte và số lượng phần tử. Chiều ngược lại có overload @@BT@@MemorySegment.copy(segment, layout, offset, array, index, count)@@BT@@ để chép một vùng segment vào mảng đã có.

@@BT@@toArray(layout)@@BT@@ là cách tiện lợi để tạo mảng mới từ toàn bộ segment. Kích thước segment phải phù hợp với kích thước phần tử của layout; ví dụ segment dành cho @@BT@@int[]@@BT@@ phải có số byte chia hết cho kích thước @@BT@@JAVA_INT@@BT@@.

Các overload sao chép giữa mảng và segment hỗ trợ @@BT@@byte[]@@BT@@, @@BT@@char[]@@BT@@, @@BT@@short[]@@BT@@, @@BT@@int[]@@BT@@, @@BT@@float[]@@BT@@, @@BT@@long[]@@BT@@ và @@BT@@double[]@@BT@@. Kiểu phần tử của mảng phải tương ứng với carrier type của layout. Nếu byte order trong layout khác native order, API có thể hoán đổi byte theo từng phần tử khi chuyển đổi.

## 6. Chuyển đổi giữa MemorySegment và ByteBuffer

@@BT@@ByteBuffer@@BT@@ vẫn phổ biến trong Java NIO. FFM API cung cấp hai phương thức để kết nối hai mô hình bộ nhớ mà không phải sao chép dữ liệu.

### Tạo ByteBuffer view từ MemorySegment

Gọi @@BT@@segment.asByteBuffer()@@BT@@ để nhận một @@BT@@ByteBuffer@@BT@@ view trên cùng vùng nhớ:

@@BT@@@@BT@@@@BT@@java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16, ValueLayout.JAVA_INT.byteAlignment());

    ByteBuffer buffer = segment.asByteBuffer()
                               .order(ByteOrder.nativeOrder());

    buffer.putInt(0x12345678);

    int value = segment.get(
        ValueLayout.JAVA_INT.withOrder(ByteOrder.nativeOrder()),
        0
    );

    System.out.println(Integer.toHexString(value)); // 12345678
}
@@BT@@@@BT@@@@BT@@

Ghi qua @@BT@@buffer@@BT@@ làm thay đổi vùng nhớ mà @@BT@@segment@@BT@@ mô tả. Không có bản sao byte trung gian.

Một số đặc điểm cần nhớ:

- @@BT@@ByteBuffer@@BT@@ mới có @@BT@@position@@BT@@ bằng 0, còn @@BT@@capacity@@BT@@ và @@BT@@limit@@BT@@ bằng kích thước segment.
- Nếu segment là native segment, buffer trả về là direct buffer.
- Nếu segment read-only, buffer cũng read-only.
- Byte order mặc định của buffer là @@BT@@BIG_ENDIAN@@BT@@. Hãy đặt @@BT@@order(...)@@BT@@ rõ ràng nếu dữ liệu cần native order hoặc một byte order khác.
- Vòng đời và giới hạn thread của buffer gắn với segment nguồn. Nếu segment thuộc một arena đã đóng, buffer view cũng không còn truy cập được.
- @@BT@@ByteBuffer@@BT@@ có capacity kiểu @@BT@@int@@BT@@, vì vậy không thể tạo buffer từ segment lớn hơn @@BT@@Integer.MAX_VALUE@@BT@@ byte. Một số heap segment, chẳng hạn segment được hỗ trợ bởi @@BT@@int[]@@BT@@, cũng không thể chuyển trực tiếp thành @@BT@@ByteBuffer@@BT@@.

### Tạo MemorySegment view từ ByteBuffer

Gọi @@BT@@MemorySegment.ofBuffer(buffer)@@BT@@ để tạo segment chia sẻ vùng nhớ của buffer:

@@BT@@@@BT@@@@BT@@java
ByteBuffer buffer = ByteBuffer.allocateDirect(32);
buffer.position(8);
buffer.limit(24);

MemorySegment remaining = MemorySegment.ofBuffer(buffer);

System.out.println(remaining.byteSize()); // 16
@@BT@@@@BT@@@@BT@@

Segment chỉ bao phủ phần dữ liệu từ @@BT@@position@@BT@@ hiện tại (bao gồm vị trí đó) đến @@BT@@limit@@BT@@ (không bao gồm giới hạn). Vì vậy trong ví dụ, segment dài 16 byte. Buffer direct tạo native segment; buffer heap tạo heap segment. Nếu buffer read-only, segment nhận được cũng read-only.

Nếu buffer được tạo từ @@BT@@MemorySegment.asByteBuffer()@@BT@@, segment chuyển ngược bằng @@BT@@ofBuffer@@BT@@ giữ cùng scope với segment ban đầu. Với buffer khác, scope tự động của segment giữ buffer còn reachable trong thời gian segment được sử dụng.

Hãy coi đây là hai view của cùng bộ nhớ. Cập nhật dữ liệu qua @@BT@@ByteBuffer@@BT@@ có thể được đọc qua @@BT@@MemorySegment@@BT@@ và ngược lại. Các thay đổi @@BT@@position@@BT@@, @@BT@@limit@@BT@@ của buffer xác định phạm vi khi tạo segment; chúng không biến thao tác này thành sao chép.

## 7. Kết hợp các thao tác trong một quy trình

Ví dụ sau sao chép dữ liệu từ mảng vào native memory, tạo lát cắt để xử lý một vùng con, điền byte 0 cho vùng đó và chuyển kết quả về mảng Java:

@@BT@@@@BT@@@@BT@@java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentTransform {

    public static int[] transform(int[] input) {
        int[] result = new int[input.length];
        if (input.length == 0) {
            return result;
        }

        try (Arena arena = Arena.ofConfined()) {
            long intSize = ValueLayout.JAVA_INT.byteSize();
            long byteSize = input.length * intSize;

            MemorySegment data = arena.allocate(
                byteSize,
                ValueLayout.JAVA_INT.byteAlignment()
            );

            MemorySegment.copy(
                input, 0,
                data, ValueLayout.JAVA_INT, 0,
                input.length
            );

            if (input.length >= 3) {
                // Bỏ qua phần tử đầu và lấy phần còn lại.
                MemorySegment tail = data.asSlice(intSize);

                // Đặt 2 phần tử đầu của tail về 0.
                long clearBytes = 2 * intSize;
                tail.asSlice(0, clearBytes).fill((byte) 0);
            }

            MemorySegment.copy(
                data, ValueLayout.JAVA_INT, 0,
                result, 0, result.length
            );
        }

        return result;
    }
}
@@BT@@@@BT@@@@BT@@

Quy trình này minh họa các điểm sau:

1. @@BT@@Arena@@BT@@ cấp phát native memory và xác định thời gian tồn tại của vùng nhớ.
2. @@BT@@MemorySegment.copy@@BT@@ chuyển các phần tử từ mảng vào segment.
3. @@BT@@asSlice@@BT@@ tạo view giới hạn trong một phần của segment.
4. @@BT@@fill@@BT@@ thay đổi byte trong vùng con.
5. @@BT@@MemorySegment.copy@@BT@@ chép kết quả về mảng Java trước khi arena đóng.

Nếu @@BT@@input@@BT@@ có ít nhất ba phần tử, hai phần tử ở vị trí 1 và 2 sẽ được đặt về 0. Các phần tử còn lại giữ nguyên. Bản thân mảng đầu vào không thay đổi vì dữ liệu đã được sao chép sang native segment.

## 8. Những giới hạn cần kiểm tra

Các thao tác trên đều có kiểm tra an toàn, nhưng chương trình vẫn cần cung cấp đúng phạm vi và layout:

- **Bounds:** offset và kích thước lát cắt phải nằm trong @@BT@@byteSize()@@BT@@ của segment. Offset trong @@BT@@MemorySegment@@BT@@ tính bằng byte; chỉ số mảng tính bằng phần tử.
- **Alignment:** truy cập bằng @@BT@@ValueLayout@@BT@@ phải thỏa mãn alignment của layout. Khi dữ liệu được đóng gói không thẳng hàng, cân nhắc layout tương ứng như @@BT@@ValueLayout.JAVA_INT_UNALIGNED@@BT@@.
- **Byte order:** overload copy theo phần tử có thể chuyển đổi byte order khi layout nguồn và đích khác nhau. Overload copy raw bytes giữ nguyên byte. @@BT@@ByteBuffer@@BT@@ mặc định @@BT@@BIG_ENDIAN@@BT@@, trong khi @@BT@@ValueLayout.JAVA_INT@@BT@@ dùng native order.
- **Read-only:** không thể ghi qua segment read-only, gọi @@BT@@fill@@BT@@ trên segment read-only hoặc dùng nó làm đích sao chép.
- **Lifetime:** native segment và các view của nó chỉ được dùng khi scope còn sống. Không trả một slice hoặc buffer view ra khỏi phạm vi @@BT@@try (Arena ...)@@BT@@ nếu arena sẽ đóng trước khi bên nhận dùng xong.
- **Thread access:** native segment dùng @@BT@@Arena.ofConfined()@@BT@@ bị giới hạn ở thread sở hữu arena. Nếu cần nhiều thread truy cập, có thể cân nhắc @@BT@@Arena.ofShared()@@BT@@ và vẫn phải đồng bộ hóa khi các thread cùng đọc/ghi vùng dữ liệu.
- **ByteBuffer size:** @@BT@@asByteBuffer()@@BT@@ không hỗ trợ segment có kích thước vượt @@BT@@Integer.MAX_VALUE@@BT@@ hoặc segment không thể biểu diễn bằng @@BT@@ByteBuffer@@BT@@.

## 9. Chọn thao tác phù hợp

| Mục tiêu | API nên dùng | Lưu ý |
|---|---|---|
| Truy cập một phần segment mà không sao chép | @@BT@@asSlice(offset, size)@@BT@@ | Offset và size tính bằng byte |
| Sao chép khối byte | @@BT@@MemorySegment.copy(src, srcOffset, dst, dstOffset, bytes)@@BT@@ | Giữ nguyên byte |
| Sao chép dữ liệu theo phần tử | @@BT@@MemorySegment.copy(...)@@BT@@ với hai @@BT@@ValueLayout@@BT@@ | Có thể hoán đổi byte theo byte order |
| Đặt toàn bộ vùng nhớ về một mẫu byte | @@BT@@fill(byte)@@BT@@ | Lặp byte trên toàn segment |
| Tạo view từ primitive array | @@BT@@MemorySegment.ofArray(array)@@BT@@ | Chia sẻ bộ nhớ với mảng |
| Tạo mảng mới từ segment | @@BT@@toArray(layout)@@BT@@ | Sao chép toàn bộ dữ liệu |
| Chép mảng vào segment hoặc segment vào mảng | Overload @@BT@@MemorySegment.copy(...)@@BT@@ nhận array | Phân biệt array index và byte offset |
| Tạo ByteBuffer view từ segment | @@BT@@asByteBuffer()@@BT@@ | Chia sẻ bộ nhớ, giới hạn kích thước của ByteBuffer |
| Tạo segment view từ ByteBuffer | @@BT@@MemorySegment.ofBuffer(buffer)@@BT@@ | Chỉ lấy vùng position đến limit |

## Kết luận

@@BT@@MemorySegment@@BT@@ cung cấp các thao tác rõ ràng cho cả view lẫn copy. Dùng @@BT@@asSlice@@BT@@, @@BT@@ofArray@@BT@@ và các phương thức chuyển đổi @@BT@@ByteBuffer@@BT@@ khi cần chia sẻ cùng vùng nhớ. Dùng @@BT@@MemorySegment.copy@@BT@@ hoặc @@BT@@toArray@@BT@@ khi cần dữ liệu độc lập. Dùng @@BT@@fill@@BT@@ khi muốn ghi một mẫu byte lên toàn vùng hoặc một lát cắt.

Khi làm việc với các API này, hãy luôn kiểm tra offset theo byte, kích thước, alignment, byte order, quyền ghi và thời gian tồn tại của segment. Những nguyên tắc đó giúp khai thác FFM API an toàn và hiệu quả trong các ứng dụng Java hiện đại.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [Java SE 22 API — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 22 API — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 API — ByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 26 API — MemorySegment](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/MemorySegment.html)
