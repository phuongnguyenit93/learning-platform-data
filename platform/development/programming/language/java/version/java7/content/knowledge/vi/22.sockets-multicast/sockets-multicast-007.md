# Socket và multicast trong Java: Chặn nguồn, hủy đăng ký và đóng kênh

## 1. Mục tiêu và bài toán thực tế

Một dịch vụ Java đang nhận UDP multicast tại nhóm `239.255.42.231` từ nhiều máy gửi. Sau một thời gian, hệ thống vận hành đưa ra ba yêu cầu độc lập:

1. **Tạm thời không nhận datagram từ một địa chỉ nguồn cụ thể** vì nguồn đó gửi quá nhiều dữ liệu, nhưng vẫn giữ đăng ký nhóm để nhận từ các nguồn khác.
2. **Thôi nhận dữ liệu của một nhóm multicast trên một giao diện mạng cụ thể**, trong khi các đăng ký nhóm khác trên cùng kênh có thể vẫn cần hoạt động.
3. **Dừng hẳn component nhận multicast**, giải phóng socket/kênh và mọi đăng ký còn tồn tại.

Ba hành động tương ứng trong Java NIO.2 là:

- **`MembershipKey.block(source)`**: chặn một nguồn trên đăng ký **any-source** đang hợp lệ, *nếu hệ điều hành hỗ trợ lọc nguồn multicast*.
- **`MembershipKey.drop()`**: hủy **một membership** do key đại diện; key trở thành vô hiệu vĩnh viễn.
- **`DatagramChannel.close()`**: đóng **toàn bộ kênh**, tự làm mất hiệu lực tất cả membership còn gắn với kênh đó và giải phóng resource.

Để **bỏ chặn** nguồn đã chặn, dùng `MembershipKey.unblock(source)`. Để chỉ nhận từ một nguồn ngay từ đầu, dùng overload **`join(group, interface, source)`**, tạo một **source-specific membership**, thay vì tạo any-source membership rồi block hàng loạt những nguồn khác.

**Phân biệt cực kỳ quan trọng:** `block()` **không** tương đương `drop()`, và `drop()` **không** tương đương `channel.close()`. Việc chặn nguồn hoặc hủy membership cũng **không** có nghĩa các datagram đã nằm trong bộ đệm socket sẽ biến mất ngay lập tức.

Các API `MulticastChannel`, `MembershipKey`, `DatagramChannel`, `block`, `unblock`, `drop` và `join` có từ **Java 7** và vẫn là phần Java NIO.2 hiện hành. Mã ví dụ hoàn chỉnh dùng **Java 17+**, biên dịch bằng `javac --release 17 -Xlint:all -Werror`; cú pháp `NetworkInterface.inetAddresses()` dạng Stream là API hiện đại, không phải cú pháp chỉ có từ Java 7.

### Sau bài học, bạn cần làm được gì?

- Giải thích đúng cách một `MembershipKey` đại diện cho nhóm, giao diện và nguồn.
- Phân biệt **ASM** (Any-Source Multicast) với **SSM** (Source-Specific Multicast).
- Biết điều kiện hợp lệ và giới hạn nền tảng của `block`/`unblock`.
- Biết khi nào dùng `drop`, khi nào dùng `close` và lúc nào phải đăng ký lại.
- Xử lý lỗi và vòng đời tài nguyên đúng, không bỏ sót cleanup.
- Thiết kế receiver có bảo vệ trước những gói đã nằm trong socket buffer.
- Kiểm thử code bằng một chương trình Java thực tế không cần gửi application datagram lên mạng.
- Nhận diện giới hạn của lọc nguồn multicast đối với tính đúng đắn và bảo mật.

## 2. Mô hình: kênh UDP, multicast group và MembershipKey

Java multicast trong NIO.2 có ba thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `DatagramChannel` | Kênh UDP để bind, gửi/nhận datagram, tham gia multicast group và đóng socket |
| `MulticastChannel` | Interface hỗ trợ `join(group, iface)` và `join(group, iface, source)`; `DatagramChannel` triển khai interface này |
| `MembershipKey` | Token đại diện cho một đăng ký cụ thể, dùng để tra cứu, lọc nguồn hoặc hủy đăng ký |

Ví dụ, cùng một `DatagramChannel` có thể tham gia hai nhóm khác nhau trên một interface, hoặc cùng nhóm trên nhiều interface nếu provider hỗ trợ. Mỗi registration có `MembershipKey` liên quan.

```text
DatagramChannel (UDP socket)
    |
    +-- MembershipKey A: group 239.255.42.231, interface eth0, any-source
    |       +-- block(192.0.2.23) nếu hỗ trợ
    |       +-- unblock(192.0.2.23)
    |       +-- drop()
    |
    +-- MembershipKey B: group 239.255.42.232, interface eth0, any-source
    |       +-- drop()
    |
    +-- MembershipKey C: group 239.255.42.233, interface eth1, source X
            +-- drop()

channel.close()  => cả A, B, C còn valid đều trở thành invalid
```

Đây là sơ đồ khái niệm, không phải cam kết máy luôn có `eth0/eth1` hoặc hỗ trợ join cùng lúc mọi tổ hợp. Tên interface tùy hệ điều hành và cấu hình mạng; có thể bị giới hạn số group, quyền và source filtering.

### 2.1. Đăng ký ASM bằng hai tham số

```java
MembershipKey key = channel.join(group, networkInterface);
```

Đoạn minh họa này nằm trong phương thức xử lý `IOException`; `channel` là `DatagramChannel` còn mở, `group` là multicast `InetAddress` tương ứng protocol family, `networkInterface` là `NetworkInterface` phù hợp.

Overload **`join(InetAddress group, NetworkInterface iface)`** tạo đăng ký **nhận từ mọi địa chỉ nguồn** gửi đến nhóm qua interface, theo các điều kiện giao mạng. `key.sourceAddress()` trả **`null`** với đăng ký này.

Đó là kiểu key có thể dùng `block(source)` hoặc `unblock(source)` **khi underlying OS hỗ trợ source filtering**.

### 2.2. Đăng ký SSM bằng ba tham số

```java
MembershipKey key =
        channel.join(group, networkInterface, allowedSource);
```

Đoạn minh họa có ba tham số được khai báo đúng kiểu và phương thức xử lý `IOException`. Overload này tạo đăng ký chỉ nhận từ **nguồn `allowedSource`**, còn gọi là **source-specific membership**; `key.sourceAddress()` trả một `InetAddress` khác `null`.

**Không gọi `block`/`unblock` lên source-specific key**: `block` ở đây ném **`IllegalStateException`** theo hợp đồng. Mô hình SSM vốn đã là **allow-list nguồn lúc join**, khác với ASM rồi dùng các lệnh loại trừ nguồn.

### 2.3. Không trộn ASM và SSM cho cùng group + interface

Theo hợp đồng `MulticastChannel`:

- Đã có đăng ký **ASM** còn hiệu lực trên cặp **(group, interface)**, việc tạo **SSM** cùng cặp đó có thể ném `IllegalStateException`.
- Đã có các đăng ký **SSM** còn hiệu lực trên cặp đó, việc join **ASM** cùng cặp có thể ném `IllegalStateException`.
- Có thể join **nhiều nguồn SSM khác nhau** cho cùng group/interface nếu hỗ trợ, mỗi đăng ký có key tương ứng.
- Gọi lại **đúng đăng ký ASM** group/interface đang tồn tại thường trả về **cùng `MembershipKey`**, không tạo hai membership độc lập.

Từ đó, đừng triển khai “giới hạn nguồn” bằng cách trộn lẫn hai kiểu key trên cùng group/interface mà không quản lý ownership và trạng thái.

## 3. Các thuộc tính của MembershipKey

Sau `join` thành công, `MembershipKey` cung cấp:

| Phương thức | Kết quả | Lưu ý |
| --- | --- | --- |
| `key.channel()` | `MulticastChannel` đã cấp membership | Vẫn trả channel ngay cả khi key invalid |
| `key.group()` | `InetAddress` nhóm multicast | Vẫn trả địa chỉ nhóm ngay cả khi key invalid |
| `key.networkInterface()` | `NetworkInterface` đăng ký | Vẫn trả interface ngay cả khi key invalid |
| `key.sourceAddress()` | Nguồn được chọn, hoặc `null` | `null` = any-source membership; khác `0.0.0.0` |
| `key.isValid()` | `boolean` | `true` khi membership còn hiệu lực; false sau drop/đóng channel |
| `key.block(source)` | Trả lại chính `MembershipKey` nếu thành công | Chỉ any-source và OS phải hỗ trợ source filtering |
| `key.unblock(source)` | Trả lại chính `MembershipKey` nếu thành công | Source phải thực sự đang bị chặn |
| `key.drop()` | `void` | Hủy membership; gọi lại trên key invalid không có tác dụng |

### 3.1. Key là một registration token, không phải packet

`MembershipKey` **không chứa datagram** và không đại diện cho một message cụ thể. Để nhận bytes, dùng `DatagramChannel.receive(ByteBuffer)` hoặc `read` khi channel đã connect theo hợp đồng.

Khóa đăng ký mô tả **quyền nhận từ nhóm/interface/nguồn**, không phải queue object chứa tất cả packet đã tới.

### 3.2. `isValid()` không bảo đảm mạng vẫn giao gói tốt

`key.isValid() == true` chỉ nói membership key còn hiệu lực trong quản lý channel, không xác nhận:

- NIC đang kết nối vật lý và hỗ trợ traffic group.
- Router/switch/firewall đang truyền datagram.
- Không có mất gói trong mạng hoặc socket buffer.
- Sender vẫn đang phát dữ liệu.
- Mọi filter đang hoạt động chính xác theo mong muốn nghiệp vụ.
- Gói từ các nguồn không bị chặn chắc chắn đến đúng ứng dụng.

Để chứng minh giao thông mạng hoạt động, phải có bài test sender–receiver, sequence numbers, quan sát packet loss và kiểm soát interface/port theo môi trường.

### 3.3. Sau invalid vẫn có metadata

Ngay cả sau `key.drop()` hoặc `channel.close()`, các getter `channel/group/networkInterface/sourceAddress` **vẫn có thể cung cấp metadata** theo hợp đồng API. Không suy từ getter còn trả về object rằng membership còn hoạt động.

**Chỉ dùng `key.isValid()` cho trạng thái sống**, đồng thời xử lý race nếu nhiều thread cùng drop/close.

## 4. Chặn một nguồn: MembershipKey.block(source)

### 4.1. Khi nào nên block?

Giả sử receiver ASM nhận từ nhiều sender. Có một sender `192.0.2.23` mà hệ thống muốn ngừng nhận datagram, nhưng vẫn nhận từ các sender khác.

```java
if (key.isValid() && key.sourceAddress() == null) {
    key.block(excludedSource);
}
```

Đây là **đoạn minh họa trong phương thức xử lý `IOException`**, với `key` và `excludedSource` đã được khai báo. Chỉ khi underlying operating system hỗ trợ source filtering và cặp địa chỉ đúng protocol family thì lệnh mới có thể thành công.

**`block(source)` không làm membership mất hiệu lực.** Receiver vẫn thuộc group/interface; hệ thống chỉ điều chỉnh danh sách nguồn bị loại trừ cho đăng ký ASM này.

### 4.2. Quy tắc địa chỉ nguồn

`source` phải là địa chỉ **unicast** hợp lệ và **cùng kiểu IP** với địa chỉ multicast group:

- Group IPv4 → source IPv4 unicast.
- Group IPv6 → source IPv6 unicast.
- Source không được là một địa chỉ multicast.
- Source không được dùng địa chỉ có family khác với group.

Nếu không đáp ứng, `block` có thể ném **`IllegalArgumentException`**.

```java
InetAddress group = InetAddress.getByName("239.255.42.231");
InetAddress source = InetAddress.getByName("192.0.2.23");
```

Đây là ví dụ địa chỉ IPv4: group thuộc dải multicast; `192.0.2.23` thuộc **TEST-NET-1, dải dành cho tài liệu và thử nghiệm**, không phải lời khuyên chặn một máy thật hay địa chỉ cần gửi packet.

Khi triển khai thực, chọn nguồn dựa trên địa chỉ sender của giao thức và xác minh nguồn hợp lệ, không lấy tùy tiện một chuỗi host chưa xác thực rồi đưa thẳng vào chính sách mạng.

### 4.3. Điều kiện hỗ trợ lọc nguồn của hệ điều hành

Lọc nguồn multicast phụ thuộc cơ chế multicast của OS/mạng, thường liên hệ tới IGMPv3 đối với IPv4 hoặc MLDv2 đối với IPv6. Tuy nhiên, việc API Java tồn tại **không bảo đảm** hệ điều hành hoặc network interface của bạn hỗ trợ đầy đủ.

`key.block(source)` có thể ném:

- `UnsupportedOperationException`: underlying OS không hỗ trợ source filtering.
- `IOException`: native I/O liên quan lọc nguồn thất bại.
- `IllegalArgumentException`: địa chỉ source không phải unicast hoặc sai family.
- `IllegalStateException`: key đã invalid hoặc key là source-specific.

**Không dùng `supportedOptions()` để kết luận `MembershipKey.block` chắc chắn dùng được.** `supportedOptions()` liệt kê socket options, còn source filtering là **năng lực của multicast membership** và OS. Phải xử lý chính lời gọi `block` và kiểm thử theo runtime.

### 4.4. Chặn cùng nguồn hai lần

Nếu source đã bị chặn và bạn gọi `block(source)` lần nữa trên cùng key, hợp đồng API quy định thao tác đó **không có hiệu ứng mới**. Điều này giúp áp dụng idempotent đối với ý định “nguồn này đang bị chặn”.

```java
key.block(source);
key.block(source); // Nếu lần thứ nhất thành công, lần thứ hai không thêm tác dụng.
```

Đoạn này cần key ASM còn valid, OS hỗ trợ source filtering và xử lý `IOException`/runtime exceptions.

### 4.5. Chặn nguồn không xóa datagram đã nằm trong bộ đệm

Theo hợp đồng `MembershipKey.block`, **sau khi block vẫn có thể nhận datagram từ nguồn đã chặn**, vì gói đó **đã vào receive buffer của socket trước khi filter có hiệu lực**.

Hệ quả:

- `block(source)` **không phải thao tác drain/clear socket buffer**.
- Nếu `receive` đã trả packet trước khi block, nghiệp vụ vẫn phải quyết định xử lý hay bỏ.
- Nếu chính sách sản phẩm cần từ chối nghiêm ngặt một nguồn ngay lúc xử lý, phải **kiểm tra địa chỉ sender ở tầng ứng dụng** dựa trên một chính sách cập nhật an toàn, ngay cả khi đã bật OS filter.
- Nếu cần xác thực sender, IP address không thay thế chữ ký/MAC, token hay xác thực nội dung phù hợp.

Một hệ thống có yêu cầu bảo mật không nên dùng lọc IP multicast làm **biện pháp bảo mật duy nhất**.

## 5. Bỏ chặn nguồn: MembershipKey.unblock(source)

`unblock(source)` cho phép nguồn trước đó đã chặn lại được nhận trong membership ASM:

```java
key.block(source);
// ... sau khi chính sách cho phép sender trở lại:
key.unblock(source);
```

Đây là đoạn minh họa trong phương thức có xử lý `IOException` cho lệnh `block`, cùng `key/source` hợp lệ.

### 5.1. `unblock` không tương đương “dỡ mọi filter”

`unblock(source)` chỉ hủy trạng thái chặn của **đúng source**. Nếu trước đó đã chặn `sourceA` và `sourceB`, unblock `sourceA` không tự bỏ chặn `sourceB`.

### 5.2. Không thể unblock nguồn chưa bị chặn

Theo API, `unblock(source)` ném **`IllegalStateException`** khi source không đang bị chặn **hoặc** key đã invalid. Đây là điểm khác với `block`: gọi `block` lặp đối với cùng nguồn đã chặn là vô hiệu, còn `unblock` lặp sau khi đã bỏ chặn thì **không phải thao tác idempotent**.

Ví dụ:

```java
key.block(source);
key.unblock(source);
key.unblock(source); // IllegalStateException.
```

Đây là ví dụ cố ý trình bày thao tác sai ở dòng cuối, không phải sequence áp dụng production nguyên trạng.

### 5.3. Nguồn vừa unblock không bảo đảm có packet mới

Unblock chỉ thay đổi điều kiện lọc; nó không phát lệnh yêu cầu sender gửi lại datagram đã mất. UDP multicast không bảo đảm giao hàng, thứ tự hay replay. Nếu ứng dụng có yêu cầu dữ liệu đầy đủ, cần sequence IDs, detection of gaps và cơ chế phục hồi ở tầng giao thức.

### 5.4. Race và state ứng dụng

Nếu nhiều thread cùng gọi block/unblock theo một bảng policy cập nhật liên tục, đừng giả định kết quả hai lệnh bất kỳ luôn diễn ra theo thứ tự mong đợi. Tốt hơn, có một **component chủ sở hữu membership** và đưa policy updates qua một queue hoặc lock điều phối. Bảng policy ứng dụng phải được đồng bộ an toàn với logic nhận/loại packet.

## 6. Hủy đăng ký: MembershipKey.drop()

`key.drop()` yêu cầu rời membership được biểu diễn bởi key:

```java
key.drop();
boolean valid = key.isValid(); // false sau drop.
```

Sau khi `drop()` trả về, key trở thành **invalid**. Không thể dùng lại key cũ để khôi phục membership. Nếu ứng dụng muốn tham gia cùng nhóm/interface lần nữa, dùng `channel.join(...)` để lấy **một key mới**.

### 6.1. Một key, một đăng ký

Khi có nhiều membership trong cùng `DatagramChannel`:

- `keyA.drop()` ngừng membership A.
- Các membership B/C khác không mặc định mất hiệu lực chỉ vì A bị drop.
- `DatagramChannel` vẫn **mở**, có thể gửi/nhận các datagram phù hợp với trạng thái còn lại.
- Nếu không còn membership nào, channel vẫn là socket UDP mở: có thể nhận datagram unicast đã bind hoặc làm việc khác theo protocol, tùy cấu hình.

**`drop()` không đóng channel.**

### 6.2. ASM và SSM khi drop

- **ASM key**: drop hủy đăng ký nhận từ **mọi nguồn** của nhóm/interface tương ứng.
- **SSM key**: drop hủy quyền nhận từ **nguồn cụ thể** của key đó; một SSM key khác cho source khác có thể tiếp tục hợp lệ.

Một SSM group/interface có thể có nhiều source-specific keys. `drop` của một key SSM không phải chỉ thị xóa mọi source-specific membership của cùng group.

### 6.3. `drop()` gọi lặp an toàn về trạng thái key

Sau khi key đã invalid, gọi `drop()` lại **không có hiệu ứng**. Một key invalid sẽ **invalid mãi mãi** — kể cả khi sau đó bạn tham gia lại cùng group/interface.

```java
MembershipKey first = channel.join(group, networkInterface);
first.drop();
first.drop(); // Không thêm tác dụng.
MembershipKey second = channel.join(group, networkInterface);
// first vẫn invalid; second là đăng ký hiện tại, nếu join thành công.
```

Đây là đoạn minh họa trong phương thức có `channel` đang mở và xử lý `IOException`. Không giữ key cũ làm tham chiếu “đăng ký đang hoạt động” chỉ vì group/interface giống nhau.

### 6.4. Sau drop vẫn có thể nhận gói đã đệm

Tài liệu `MembershipKey.drop` nhấn mạnh rằng **sau drop vẫn có thể nhận datagram của nhóm đã rời**, do gói đã có mặt trong receive buffer. Vì vậy không suy “drop rồi thì không bao giờ thấy packet group đó nữa” từ một `receive` ngay sau lệnh.

Nếu phải xử lý chính sách ngay tại application boundary, kiểm tra source/group/application identity theo khả năng giao thức, và chuyển trạng thái receiver sang không nhận công việc mới trước khi cleanup.

### 6.5. Khi nào drop phù hợp hơn close?

Dùng `drop` khi:

- Một người dùng bỏ đăng ký một topic/group.
- Ứng dụng còn cần giữ UDP socket và các membership khác.
- Bạn muốn thay đổi group/interface nhưng có thể dùng lại socket.
- Bạn đang kiểm thử việc hủy rồi đăng ký lại một group.

Dùng `close` khi cả subsystem kết thúc hoặc socket không còn owner khác sử dụng.

## 7. Đóng kênh: DatagramChannel.close()

Khi `channel.close()`:

- Kênh UDP đóng.
- Mọi membership còn gắn với kênh đều bị **drop** và các `MembershipKey` liên quan thành invalid.
- Các resource socket được giải phóng theo vòng đời channel và OS.
- Các thao tác I/O sau close thất bại theo hợp đồng `Channel`/`DatagramChannel`.
- Muốn nhận tiếp về sau, phải **mở một channel mới**, bind/join lại, tạo các key mới và thiết lập lại option/receiver state.

```java
DatagramChannel channel = DatagramChannel.open();
try {
    // Bind, join, receive, xử lý.
} finally {
    channel.close();
}
```

Đây là mẫu minh họa trong phương thức có xử lý `IOException`; ví dụ thật bên dưới dùng `try-with-resources` để giảm nguy cơ quên close.

### 7.1. Try-with-resources là lựa chọn nền tảng

```java
try (DatagramChannel channel = DatagramChannel.open()) {
    // Join group và dùng MembershipKey trong scope này.
}
// Ra khỏi scope sẽ đóng channel.
```

`DatagramChannel` triển khai `AutoCloseable/Closeable` qua channel hierarchy. `try-with-resources` gọi close kể cả khi phần xử lý trong khối ném exception.

Nếu trong cùng khối có nhiều membership, không cần bắt buộc gọi `drop()` từng key **chỉ để tránh rò rỉ khi đóng toàn bộ channel**: `close` đã làm invalid tất cả. Tuy vậy, **drop tường minh** hữu ích khi nghiệp vụ yêu cầu rời một group **trước** khi toàn bộ channel kết thúc hoặc để mô tả intent rõ ràng.

### 7.2. Đóng channel khác với ngắt thread nhận

Nếu một thread đang `DatagramChannel.receive(...)` ở blocking mode, việc đóng kênh từ thread khác có cơ chế I/O interruption/close theo hợp đồng channel và có thể làm phép chờ kết thúc với exception phù hợp. Không viết code cho rằng việc gọi `drop` hoặc `block` sẽ tự động đánh thức một phép `receive` đang blocked khi không còn gói.

Nếu ứng dụng cần dừng consumer có kiểm soát, xác định:

1. Ai sở hữu channel?
2. Ai giữ và thao tác `MembershipKey`?
3. Có một receiver thread hay nhiều thread?
4. Khi shutdown, có cần bỏ qua tất cả packet mới, hay drain queue?
5. Thread đang blocking thì dùng close, non-blocking selector hoặc cơ chế điều phối tương ứng như thế nào?
6. Sau khi close, owner có chờ worker kết thúc bằng join/await với deadline không?

**`close()` và `join()/await` của Java threads là hai bước khác nhau**: đóng resource không tự chứng minh toàn bộ ứng dụng đã hoàn tất xử lý packet.

### 7.3. Đừng tiếp tục dùng membership key cũ sau close

Ví dụ:

```java
MembershipKey active;
try (DatagramChannel channel = DatagramChannel.open()) {
    // active = channel.join(...);
}
// active.isValid() sẽ false nếu active đã từng được join vào channel này.
```

Đây là đoạn code phác họa, vì `active` phải được khởi tạo từ `join` và các biến tham số chưa có. Không giữ key để dùng lại sau scope.

### 7.4. Đóng nhiều lần và ownership

Một channel đã đóng không thể mở lại bằng `join`. `close()` là thao tác cleanup có thể được gọi lại theo hợp đồng idempotent của channel, nhưng ứng dụng vẫn nên xác định một owner chính, không để nhiều component tự ý đóng channel chia sẻ khi bên khác còn cần dùng.

## 8. Bảng phân biệt ba thao tác chính

| Yêu cầu | `block(source)` | `drop()` | `channel.close()` |
| --- | --- | --- | --- |
| Phạm vi | Một source của **một ASM membership** | Một membership | Mọi membership và socket của channel |
| Membership key sau lệnh | Vẫn valid | Invalid | Tất cả key của channel invalid |
| Nhận từ source khác cùng group | Có thể tiếp tục | Không còn qua membership đó | Không, channel đã đóng |
| Các group khác trên cùng channel | Không bị hủy | Không bị hủy chỉ vì key này drop | Bị hủy |
| Có thể đảo ngược? | `unblock(source)` nếu key valid và nguồn đang blocked | Phải `join` lại để lấy key mới | Phải mở channel mới và join lại |
| Cần OS source filtering? | **Có** | Không phải cơ chế source filtering | Không phải cơ chế source filtering |
| Có thể còn gói đã buffered? | **Có** | **Có** | Không được dùng channel đã đóng để nhận tiếp |
| Có tự phát datagram multicast? | Không | Không | Không |
| Phù hợp với | Chặn một sender | Rời một nhóm/nguồn đăng ký | Shutdown toàn bộ receiver |

### 8.1. `unblock` là thao tác thứ tư, không phải “undo drop”

`unblock(source)` chỉ xóa trạng thái chặn nguồn trên key ASM **còn valid**. Sau `drop` hoặc `close`, key invalid; `unblock` không thể hồi sinh membership. Muốn đăng ký lại dùng đúng overload của `join`.

### 8.2. “Hủy đăng ký” không xóa bảng policy nghiệp vụ

Nếu ứng dụng giữ một map nguồn đã cấm, gọi `drop()` không tự xóa map đó. Ngược lại, khi rejoin group và nhận key mới, các filter đã đặt trên key cũ không nên được giả định tự mang sang key mới.

Cần đồng bộ trạng thái “desired policy” ở application level, rồi áp dụng lại nếu membership được tạo mới. Nếu OS không hỗ trợ source filtering, có thể lọc sender địa chỉ ở tầng ứng dụng theo nhu cầu, nhưng điều này **không tiết kiệm băng thông/đường mạng** như filter ở tầng hệ thống và không là một xác thực sender.

## 9. Các ngoại lệ cần xử lý đúng

### 9.1. Khi join

`channel.join(group, iface)` và `join(group, iface, source)` có thể thất bại bởi:

- `IllegalArgumentException` nếu group không phải multicast, protocol family sai, hoặc source-specific address không phải unicast/sai family.
- `IllegalStateException` nếu đăng ký ASM/SSM cùng group/interface đang xung đột.
- `UnsupportedOperationException` nếu môi trường không hỗ trợ multicast/source-specific filtering.
- `ClosedChannelException` nếu channel đã đóng.
- `IOException` từ hệ điều hành.
- `SecurityException` trong những môi trường Java/provider có kiểm soát quyền theo cơ chế tương ứng.

Không biến mọi lỗi này thành thông báo “group không tồn tại”. Đó có thể là lỗi cấu hình, provider, quyền, trạng thái socket hoặc lifecycle.

### 9.2. Khi block

| Loại | Nguyên nhân |
| --- | --- |
| `IllegalArgumentException` | Source không phải unicast hoặc sai address family |
| `IllegalStateException` | Membership là SSM hoặc key invalid |
| `UnsupportedOperationException` | Native OS không hỗ trợ source filtering |
| `IOException` | Lỗi I/O khi cập nhật filter |

Một kiểm tra `key.isValid()` trước `block` hữu ích cho diagnostics nhưng **không thay thế xử lý lỗi**: thread khác có thể drop/close key ngay sau check.

### 9.3. Khi unblock

Theo chữ ký API, `unblock(source)` không khai báo checked `IOException`; nó có thể ném `IllegalStateException` khi nguồn không bị chặn hoặc key invalid. Không gọi `unblock` trên SSM key rồi tin đó là chức năng chọn nguồn của SSM: SSM không dùng bộ thao tác block/unblock.

### 9.4. Khi drop hoặc close

`drop()` không khai báo checked exception và không có hiệu ứng khi key invalid. `DatagramChannel.close()` có thể ném `IOException` theo hợp đồng. Vì vậy `try-with-resources` giúp cleanup nhưng cũng phải không nuốt lỗi trong quá trình đóng nếu ứng dụng cần biết việc shutdown đã thành công.

### 9.5. Đừng phân loại lỗi bằng chuỗi message

Message lỗi có thể thay đổi theo OS/JDK/locale. Ưu tiên **kiểu exception** và ngữ cảnh: group/interface, loại membership ASM/SSM, source hợp lệ, channel đã đóng hay chưa và chính sách stop.

## 10. Chọn interface và protocol family đúng

### 10.1. IPv4 / IPv6

Đăng ký multicast group cần đúng family:

```java
try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    // Dùng group/source IPv4 và IPv4-capable NetworkInterface.
}
```

Đây là đoạn minh họa trong phương thức có `throws IOException`. `StandardProtocolFamily.INET` tương ứng IPv4. Với nhóm IPv6, cân nhắc `StandardProtocolFamily.INET6` và interface có khả năng IPv6. Không tự giả định một channel IPv6 có thể join group IPv4 trên mọi hệ điều hành.

### 10.2. Bind địa chỉ wildcard

Để nhận multicast, tài liệu `MulticastChannel` khuyến nghị bind socket tới **wildcard address**; nếu bind vào một địa chỉ cụ thể, việc nhận gói multicast có thể phụ thuộc implementation.

```java
channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
channel.bind(new InetSocketAddress(0));
```

Đây là đoạn minh họa với channel IPv4 đã mở. Cổng `0` cho OS chọn một ephemeral port, phù hợp để thử lifecycle **không gửi/nhận dữ liệu nghiệp vụ**. Receiver thực phải bind đúng port mà sender dùng, và cần thiết kế `SO_REUSEADDR`/`SO_REUSEPORT` phù hợp với OS cùng yêu cầu nhiều process.

Không mặc định chỉ cần bind port 0 là có thể nhận gói multicast của một hệ thống thật: sender thường phát vào một port cụ thể.

### 10.3. Chọn NetworkInterface

Một cách khám phá interface:

```java
for (NetworkInterface iface :
        java.util.Collections.list(NetworkInterface.getNetworkInterfaces())) {
    if (iface.isUp() && iface.supportsMulticast()) {
        System.out.println(iface.getName());
    }
}
```

Đây là đoạn minh họa trong phương thức xử lý `SocketException`; interface còn cần đúng protocol family và interface address phù hợp. Có máy có nhiều NIC/VPN/bridge và loopback khác nhau. **`supportsMulticast()==true` không tự bảo đảm có routing multicast tới group mong muốn**.

Ứng dụng production nên có cấu hình interface rõ thay vì chọn “NIC đầu tiên” từ enumeration. Ví dụ chạy được ở mục 12 chọn NIC phù hợp để kiểm tra API, không phải mô hình lựa chọn interface tối ưu cho mọi môi trường.

### 10.4. Cấu hình TTL và interface gửi không thay membership filtering

`IP_MULTICAST_IF` chọn interface **gửi** multicast; `IP_MULTICAST_TTL` định phạm vi hop-limit cho datagram được gửi. Chúng không phải cách thay thế `MembershipKey.block`/`unblock`/`drop`.

**SO_BROADCAST cũng không phải multicast membership**: UDP broadcast khác UDP multicast. Không dùng `setOption(SO_BROADCAST,true)` như cách tham gia group.

## 11. Ví dụ Java 17+ hoàn chỉnh, đã chạy với multicast membership thật

Ví dụ sau dùng một **multicast-capable IPv4 network interface** đang hoạt động. Nó không gửi **application datagram**; nhưng thao tác join/drop có thể tạo **thông báo điều khiển membership ở tầng mạng** (như IGMP), nên chỉ chạy trên môi trường mạng mà bạn được phép thực hiện kiểm thử.

Mục tiêu chương trình:

1. Dò một interface đang `isUp()`, `supportsMulticast()`, không phải loopback và có địa chỉ IPv4 unicast phù hợp.
2. Nếu không có interface thích hợp, in trạng thái **SKIPPED** thay vì giả vờ đã thử multicast.
3. Mở `DatagramChannel` IPv4, bật `SO_REUSEADDR` và bind ephemeral port.
4. Join ASM group `239.255.42.231` và kiểm chứng `isValid()`, `sourceAddress()==null`, group, interface, channel.
5. Join lại đúng group/interface để xác minh trả về cùng key đang còn valid.
6. Gọi `block` đối với địa chỉ mẫu `192.0.2.23`; nếu native filtering hỗ trợ thì gọi block lần hai để xác minh idempotence, rồi `unblock`. Gọi `unblock` lần hai phải ném `IllegalStateException`.
7. Nếu OS không hỗ trợ filtering hoặc native I/O thất bại, báo **UNAVAILABLE** để demo tiếp tục kiểm thử lifecycle. Khi đưa vào production phải **phân biệt UnsupportedOperationException với IOException** để có hành động thích hợp.
8. `drop()` key, xác minh invalid; drop lần hai không tác dụng; metadata của key invalid vẫn truy vấn được.
9. Gọi `block` trên key invalid và xác minh `IllegalStateException`.
10. Join lại và nhận **key mới**, không sử dụng key cũ.
11. Ra khỏi `try-with-resources` đóng DatagramChannel và xác minh key mới invalid.

**Tính khả chuyển:** Kết quả `source filtering = SUPPORTED` phụ thuộc OS, kernel và network interface. Bài test này không xác minh traffic thật từ sender vì không gửi packet; nó xác minh hành vi các lời gọi API và trạng thái key.

### 11.1. Mã đầy đủ: `MulticastMembershipDemo.java`

```java
import java.io.IOException;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.util.Enumeration;

public final class MulticastMembershipDemo {
    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    private static NetworkInterface suitableInterface() throws SocketException {
        Enumeration<NetworkInterface> entries =
                NetworkInterface.getNetworkInterfaces();
        if (entries == null) return null;

        while (entries.hasMoreElements()) {
            NetworkInterface nic = entries.nextElement();
            if (!nic.isUp() || !nic.supportsMulticast() || nic.isLoopback()) {
                continue;
            }
            boolean ipv4 = nic.inetAddresses().anyMatch(
                    address -> address instanceof Inet4Address
                            && !address.isLoopbackAddress());
            if (ipv4) return nic;
        }
        return null;
    }

    public static void main(String[] args) throws Exception {
        NetworkInterface nic = suitableInterface();
        if (nic == null) {
            System.out.println("integration = SKIPPED_NO_MULTICAST_INTERFACE");
            return;
        }

        InetAddress group = InetAddress.getByName("239.255.42.231");
        InetAddress excluded = InetAddress.getByName("192.0.2.23");

        MembershipKey afterClose;
        try (DatagramChannel channel =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0));

            MembershipKey key = channel.join(group, nic);
            check(key.isValid(), "initial key");
            check(key.sourceAddress() == null, "any-source membership");
            check(key.group().equals(group), "group");
            check(key.networkInterface().equals(nic), "interface");
            check(key.channel() == channel, "channel identity");
            System.out.println("any-source valid = true");
            System.out.println("metadata = PASS");

            MembershipKey repeated = channel.join(group, nic);
            check(repeated == key, "repeated join returns key");
            System.out.println("same join reused = true");

            boolean filterSupported;
            try {
                check(key.block(excluded) == key, "block return key");
                check(key.block(excluded) == key, "duplicate block");
                check(key.unblock(excluded) == key, "unblock return key");
                try {
                    key.unblock(excluded);
                    throw new AssertionError("duplicate unblock must fail");
                } catch (IllegalStateException expected) {
                    System.out.println("duplicate unblock rejected = true");
                }
                filterSupported = true;
            } catch (UnsupportedOperationException unsupported) {
                filterSupported = false;
            } catch (IOException filteringError) {
                filterSupported = false;
            }

            System.out.println("source filtering = "
                    + (filterSupported ? "SUPPORTED" : "UNAVAILABLE"));

            key.drop();
            check(!key.isValid(), "key invalid after drop");
            key.drop();
            check(!key.isValid(), "drop idempotent");
            check(key.channel() == channel && key.group().equals(group)
                    && key.networkInterface().equals(nic),
                    "metadata after drop");
            System.out.println("drop invalidates key = true");
            System.out.println("drop idempotent = true");

            try {
                key.block(excluded);
                throw new AssertionError("invalid key must not filter");
            } catch (IllegalStateException expected) {
                System.out.println("block invalid key rejected = true");
            }

            MembershipKey next = channel.join(group, nic);
            check(next.isValid() && next != key,
                    "new membership after drop");
            System.out.println("rejoin valid new key = true");
            afterClose = next;
        }

        check(!afterClose.isValid(), "close invalidates key");
        System.out.println("close invalidates key = true");
        System.out.println("checks = PASS");
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 MulticastMembershipDemo.java
java MulticastMembershipDemo
```

### 11.2. Stdout của lượt chạy thực tế trên Windows/JDK 17

Trong môi trường đã thử nghiệm, có IPv4 multicast-capable NIC và hỗ trợ source filtering. Kết quả là:

```text
any-source valid = true
metadata = PASS
same join reused = true
duplicate unblock rejected = true
source filtering = SUPPORTED
drop invalidates key = true
drop idempotent = true
block invalid key rejected = true
rejoin valid new key = true
close invalidates key = true
checks = PASS
```

**Đây là kết quả cụ thể của máy kiểm thử**, không phải output bất biến trên mọi môi trường. Nếu không có interface, chương trình in `integration = SKIPPED_NO_MULTICAST_INTERFACE`; nếu hỗ trợ multicast nhưng không hỗ trợ source filtering, có thể in `source filtering = UNAVAILABLE` rồi vẫn hoàn thành những kiểm tra vòng đời.

### 11.3. Vì sao không gửi datagram?

Để kiểm chứng `MembershipKey.block/unblock/drop/close` và trạng thái key, không cần phát một gói tin ứng dụng lên mạng. Điều này giảm rủi ro gây ảnh hưởng ngoài ý muốn trong demo. Tuy nhiên **join/drop vẫn tương tác với hệ thống mạng**, nên chỉ chạy ở môi trường được phép và không nhầm đây là unit test thuần bộ nhớ.

Để kiểm chứng một nguồn **thật sự bị lọc khỏi traffic**, cần integration test với sender/receiver do mình quản lý, interface và địa chỉ được phép sử dụng, sequence numbers và các mức policy. Một số datagram đã buffered có thể vẫn được nhận sau block/drop.

### 11.4. Vì sao dùng địa chỉ `192.0.2.23`?

Đây là địa chỉ thuộc dải **TEST-NET-1** dành cho tài liệu, chỉ dùng làm đối số một địa chỉ unicast cùng family trong bài demo. Không gửi packet tới địa chỉ đó, cũng không giả định nó là sender hiện hữu trên mạng.

Trong production, source cần được lấy từ policy có cấu hình/đăng ký thực tế và được validate.

### 11.5. Tại sao cùng group/interface join lại trả key cũ?

Khi đã có membership ASM, yêu cầu join ASM giống hệt không tạo thêm membership riêng. API trả lại key đại diện cho registration đã có. Nếu muốn hủy membership đó, phải hiểu **tất cả thành phần sử dụng key** trước khi gọi `drop`. Đừng nghĩ hai chỗ gọi join tạo hai reference-counted registrations độc lập.

### 11.6. Tại sao `drop` lần hai không ném lỗi?

Theo hợp đồng, drop trên key invalid **không có tác dụng**. Điều này khác với `unblock` hai lần: lần thứ hai không còn nguồn đang bị block và ném `IllegalStateException`.

### 11.7. Vì sao sau rejoin phải dùng key mới?

Key đã invalid **không thể valid trở lại**. Rejoin cùng group/interface trả một membership token mới. Mọi map/callback/policy object của ứng dụng phải cập nhật tới key mới. Demo kiểm chứng `next != key`.

### 11.8. Tại sao key invalid sau close?

`DatagramChannel.close()` đóng socket và tự hủy những membership còn tồn tại. Đối tượng `MembershipKey` đã lưu trong biến `afterClose` vẫn có thể được hỏi `isValid()` nhưng trả `false`. Không được dùng lại để nhận datagram hoặc block/unblock; muốn hoạt động phải mở channel và join mới.

### 11.9. Lưu ý về lỗi trong demo

Để vẫn thử được `drop/close` trên OS thiếu filter, ví dụ gộp **`UnsupportedOperationException` và `IOException`** ở riêng nhánh thử filter thành kết quả `UNAVAILABLE`. Đây là **lựa chọn của demo**, không phải quy tắc phân loại lỗi cho production. Ứng dụng thật nên ghi nhận riêng: OS không hỗ trợ (có thể fallback) và lỗi I/O (có thể cần báo động/retry), không mặc định chúng là một.

## 12. Ví dụ bổ sung: SSM và lý do block không hợp lệ

Nếu muốn chỉ nhận từ một nguồn xác định ngay từ đầu, dùng:

```java
InetAddress group = InetAddress.getByName("239.255.42.232");
InetAddress allowed = InetAddress.getByName("192.0.2.23");

try (DatagramChannel dc =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    dc.bind(new InetSocketAddress(0));

    MembershipKey ssm = dc.join(group, nic, allowed);
    try {
        System.out.println(ssm.sourceAddress().equals(allowed));
        try {
            ssm.block(allowed); // IllegalStateException trên SSM key.
        } catch (IllegalStateException expected) {
            System.out.println("SSM cannot block another source");
        }
    } finally {
        ssm.drop();
    }
}
```

Đây là **đoạn minh họa trong phương thức có xử lý `IOException`**, với biến `nic` là một `NetworkInterface` IPv4 thực, đã `isUp` và phù hợp multicast. Nếu platform không hỗ trợ source-specific filtering, `join(group,nic,allowed)` có thể ném `UnsupportedOperationException` trước khi có key.

Trong một lượt kiểm thử Java 17 riêng với một interface hỗ trợ, `join` trả SSM key có `sourceAddress` khớp, `ssm.block(...)` ném `IllegalStateException` và `ssm.drop()` làm key invalid. Đây là **kiểm thử thứ hai**, không phải một nhánh đã chạy trong `MulticastMembershipDemo.java` ở mục 11.

### 12.1. Vì sao không dùng ASM rồi block tất cả trừ một nguồn?

Để xây dựng danh sách cho phép một nguồn, bạn không biết trước mọi source khác trên Internet/mạng; một danh sách chặn không thể bao quát mọi địa chỉ có thể gửi. Nếu OS hỗ trợ, SSM qua `join(group, iface, source)` biểu đạt **allow one source** rõ ràng hơn.

ASM + `block(source)` phù hợp với **loại trừ một số nguồn xác định**, không phải một cơ chế allow-list nguồn tuyệt đối. Nếu tính năng bắt buộc source-based policy mà OS không hỗ trợ SSM, application cần quy trình fallback và bảo mật bổ sung, không chỉ giả định ASM filter có khả năng tương đương.

### 12.2. Có thể nhiều SSM keys cho nhiều nguồn?

`MulticastChannel.join(group, iface, source)` hỗ trợ đăng ký từ nhiều nguồn khác nhau cho cùng group/interface theo hợp đồng khi platform hỗ trợ. Mỗi key đại diện một nguồn. Để thôi nhận từ một nguồn, gọi `drop()` lên key của nguồn đó; các key nguồn khác không bị hủy theo cách đó.

### 12.3. Không bao giờ unblock SSM để thêm nguồn

`unblock(source)` chỉ có nghĩa với nguồn đã bị chặn **bằng `block` trên ASM key**. Muốn cho phép một nguồn mới trong SSM, join source-specific membership cho nguồn đó (nếu chưa có). Muốn bỏ một nguồn, drop đúng key của nguồn đó.

## 13. Thiết kế component thực tế với quyền sở hữu rõ ràng

Một receiver production có thể quản lý cấu trúc trạng thái:

```text
ReceiverOwner
  - DatagramChannel socket
  - Map<GroupInterface, MembershipKey> asmMemberships
  - Map<GroupInterfaceSource, MembershipKey> ssmMemberships
  - DesiredSourcePolicy policyStore
  - ReceiverWorker
  - ShutdownState
```

Đây là mô hình khái niệm, không phải các lớp Java có sẵn. Mục đích là tránh phân tán `join/drop/close` tới nhiều nơi khiến state lệch hoặc một component vô tình đóng channel của component khác.

### 13.1. Quy trình chặn nguồn

1. Người vận hành yêu cầu chặn một nguồn hợp lệ.
2. Xác thực quyền thay đổi policy và normalize địa chỉ IPv4/IPv6.
3. Xác định membership ASM đúng group/interface.
4. Ghi intent vào policy store nếu ứng dụng cần giữ sau restart.
5. Nếu OS hỗ trợ, gọi `key.block(source)`; xử lý `IllegalStateException`/`UnsupportedOperationException`/`IOException`.
6. Bắt đầu **lọc bổ sung ở tầng ứng dụng** nếu cần chặn ngay những datagram đã vào queue.
7. Quan sát metrics packet accepted/rejected và tình trạng receiver.
8. Khi policy thay đổi, `unblock` đúng source đã chặn hoặc cập nhật SSM membership theo giao thức tương ứng.

### 13.2. Quy trình rời một group

1. Đánh dấu group/interface không còn được đăng ký.
2. Ngừng đưa datagram mới của group đó vào downstream processing theo policy.
3. `key.drop()`, xác minh `!key.isValid()` nếu cần.
4. Loại key khỏi map quản lý, không dùng tham chiếu invalid.
5. Không giả định socket buffer đã trống hoàn toàn.
6. Các membership khác vẫn được giữ nếu channel chưa đóng.

### 13.3. Quy trình shutdown toàn bộ

1. Owner chuyển sang trạng thái `STOP_REQUESTED`, ngừng nhận các subscription mới.
2. Thông báo receiver worker dừng theo cơ chế thread-safe.
3. Đóng channel bằng `close()` hoặc cho try-with-resources kết thúc; mọi membership invalid.
4. Worker bắt exceptions do close/interruption hợp lệ theo chính sách shutdown, không che lỗi ngoài dự kiến.
5. Chờ worker kết thúc với timeout/deadline.
6. Cleanup queue, buffer, downstream resources và trạng thái, không báo `STOPPED` quá sớm.
7. Nếu sẽ restart, mở channel mới, bind lại, join lại các group và **áp dụng lại desired policy**; không sử dụng key cũ.

### 13.4. Khi nhiều thread cùng dùng channel

Membership methods có thể được gọi từ nhiều thread; hành động drop/close có thể cạnh tranh với block/unblock hoặc receive. Đừng cho mọi thread tự thao tác tùy ý; đặt một owner/command queue để serialize các thay đổi membership nếu cần và đồng bộ policy-state.

Ngay cả khi có `key.isValid()` precheck, một thread khác có thể đóng channel ngay sau check. Vì vậy phải xử lý exception tại chính `block`/`unblock`/`join` và không dựa vào “đã check là chắc chắn thành công”.

### 13.5. Quan hệ giữa key và socket buffer

Receiver có thể đã nhận một datagram, hoặc packet còn nằm trong socket receive buffer khi policy thay đổi. OS-level block/drop **không tạo một hàng rào giao dịch** giữa packet nhận trước và packet nhận sau.

Nếu app cần policy nghiêm ngặt theo timestamp/version, hãy gắn version cho policy và phân loại packet tại boundary ứng dụng. Khi yêu cầu tính đúng đắn mạnh, giao thức cần các trường sequence/source identity và hệ thống xác thực phù hợp; chỉ nhìn nguồn IP có thể không đủ.

## 14. Phạm vi và bảo mật: multicast filtering không phải access control

Lọc nguồn multicast giúp quản lý việc **tiếp nhận gói theo địa chỉ IP** ở mức hệ điều hành nếu hỗ trợ, nhưng:

- Source IP có thể bị giả mạo trong những môi trường mạng thiếu bảo vệ.
- Dữ liệu từ sender đã chặn có thể đã nằm trong receive buffer.
- Một chính sách lọc có thể không được OS hỗ trợ; việc fallback cần được quyết định có chủ đích.
- `drop()`/`close()` thay đổi membership/socket, không xóa dữ liệu đã phát sinh tại consumer hoặc downstream.
- Không có bảo đảm về giao hàng/khôi phục gói UDP bị mất.
- Một group multicast không tự có cơ chế mã hóa hoặc xác thực.

Nếu hệ thống truyền dữ liệu nhạy cảm, thiết kế kiểm soát quyền, xác thực thông điệp và mã hóa theo giao thức được phép; đừng quảng bá `key.block(source)` là công cụ chống tấn công mạng hoàn chỉnh.

### 14.1. Không suy từ group address rằng traffic an toàn

Nhóm `239.255.42.231` trong demo chỉ là một địa chỉ multicast IPv4 dùng để kiểm thử. Trong hệ thống thật, lựa chọn group/port/interface cần tính tới phân vùng mạng và chính sách multicast routing. Không gửi datagram thử vào một group ngoài quyền quản lý hoặc port có dịch vụ đang dùng.

### 14.2. NetworkInterface hiện diện không bảo đảm hoạt động

`supportsMulticast()==true` là một thông tin khả năng của NIC/provider, không đảm bảo IGMP/MLD, switch, firewall, multicast routing và TTL đã được cấu hình đúng. Nên dùng integration test có sender và receiver trong mạng được quản lý trước khi phụ thuộc vào filter của một OS.

## 15. Sai lầm thường gặp

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| `block(source)` rời multicast group | Nó chỉ lọc một nguồn trên ASM membership | Dùng `drop` để rời membership |
| `block` đóng socket | Channel vẫn mở | `channel.close` mới đóng toàn bộ kênh |
| Có `block` trong API nên OS nào cũng hỗ trợ | Source filtering là tùy chọn native | Catch `UnsupportedOperationException` và test |
| `supportedOptions` có multicast option thì `block` chắc chạy | Socket options khác khả năng membership filtering | Thử chính API `block` |
| `block` trên SSM key là cách thêm nguồn bị chặn | SSM không cho `block` | Dùng ASM + block hoặc SSM join source |
| `sourceAddress()==null` nghĩa nguồn gửi có IP null | Null là đặc tính ASM membership | Không nhầm metadata key với packet sender |
| `unblock` hai lần giống `block` hai lần | Lần 2 thường ném `IllegalStateException` | Theo dõi policy/source |
| `drop` nhiều lần ném lỗi | Drop trên invalid không tác dụng | Được dùng cleanup idempotent |
| Key invalid có thể reset lại bằng `join` trên object cũ | `MembershipKey` không có cơ chế revive | Rejoin trên channel và lấy key mới |
| `drop` một key làm mọi group dừng | Phạm vi là membership của key đó | Đóng channel mới làm mọi key invalid |
| Đóng channel vẫn giữ được MembershipKey để dùng tiếp | Key invalid khi channel đóng | Mở channel mới, join lại |
| Không nhận được packet ngay nghĩa source đã bị block thành công | Cũng có thể không có sender/routing | Kiểm chứng API và traffic test riêng |
| Sau block không thể nhận packet nguồn cũ | Packet có thể đã buffered | Có policy filter tại app boundary |
| Sau drop không thể thấy packet group đã rời | Packet có thể đã buffered | Không đồng nhất drop với clear buffer |
| `key.isValid()` chứng minh mạng hoạt động | Chỉ lifecycle của key | Test sender/receiver và packet delivery |
| Lọc IP thay authentication | IP không phải chứng cứ bảo mật đủ mạnh | Xác thực thông điệp và policy |
| Có một NIC up là đủ để join mọi multicast group | Còn family, quyền, route, OS support | Validate NIC/group/port |
| Group IPv4 dùng source IPv6 trong `block` | Sai family | Cùng protocol family |
| Source là multicast address | Phải là unicast | Validate source trước block/join SSM |
| SSM join thành công thì mọi source filtering kiểu ASM cũng đúng | Hai mode có semantics khác | Đo từng API và state |
| Lặp `join` ASM tạo hai key độc lập | Trả key đại diện membership sẵn có | Quản lý owner/group-interface |
| `close` thay thế toàn bộ cleanup worker | Đóng resource chưa chắc task/queue xong | Join/await workers và cleanup |
| Chặn source ở OS thì không mất packet hợp lệ | Buffer/OS/network có thể drop | Metrics và recovery protocol |
| Chỉ cần `SO_BROADCAST` cho multicast | Broadcast khác multicast | Dùng `join` + `MembershipKey` |
| Chọn interface đầu tiên cho production | Có thể là VPN/bridge/không đúng route | Chọn interface theo cấu hình |
| Không cần xử lý `IOException` khi block | API có thể fail vì native I/O | Propagate, báo lỗi, fallback phù hợp |
| Tất cả output của demo phải giống nhau | NIC/OS/filter khác nhau | Phân biệt kết quả môi trường |
| `drop`/`close` gửi datagram ứng dụng để “unsubscribe” | Không phải application data protocol | Hành vi có thể tạo control-plane messages |
| Source filter tắt cần restart toàn bộ JVM | Có thể điều phối membership hoặc app-level policy | Thiết kế fallback và resource lifecycle |

## 16. Bài tập kèm đáp án

### Bài 1 — Ba hành động

Receiver muốn tạm ngừng nguồn S1 nhưng vẫn nhận nguồn S2 trong cùng group. Nên dùng `block`, `drop` hay `close`?

**Đáp án:** Nếu key là **ASM** và OS hỗ trợ lọc nguồn, dùng `key.block(S1)`. `drop` sẽ hủy membership group/interface, còn `close` đóng toàn bộ socket.

### Bài 2 — Key source-specific

Một key có `sourceAddress()!=null`. Có nên gọi `key.block(S2)` trên key này?

**Đáp án:** Không. Đó là source-specific key; `block` trên loại này ném `IllegalStateException`. Muốn allow-list source, dùng chính `join(group,iface,source)` và quản lý key SSM.

### Bài 3 — Source address hợp lệ

Group là IPv4 `239.255.42.231` nhưng source truyền vào `block` là một địa chỉ IPv6. Điều gì xảy ra?

**Đáp án:** `IllegalArgumentException` vì source không cùng loại địa chỉ IP với group. Source cũng phải là unicast, không phải một multicast address.

### Bài 4 — Khả năng nền tảng

`key.block(S1)` ném `UnsupportedOperationException`. Có thể thử `supportedOptions()` để “bật” source filtering không?

**Đáp án:** Không. Source filtering là năng lực OS/native multicast membership, không phải chỉ một socket option có thể tự thêm vào `Set`. Cần fallback được chấp nhận, điều kiện triển khai phù hợp và có thể lọc sender tại ứng dụng.

### Bài 5 — Hai lần block

Đã `key.block(S1)` thành công, lại gọi `key.block(S1)`. Kết quả theo hợp đồng?

**Đáp án:** Nếu S1 đang bị chặn, lần block lặp không có tác dụng thêm. Không tự tạo hai filter cần unblock hai lần.

### Bài 6 — Hai lần unblock

Đã `key.block(S1)` rồi `key.unblock(S1)` thành công. Sau đó lại `unblock(S1)`. Kết quả?

**Đáp án:** `IllegalStateException` vì S1 hiện không còn bị chặn; đây khác hành vi block lặp.

### Bài 7 — Drop một nhóm

Một DatagramChannel tham gia hai group trên cùng NIC bằng key A và key B. Gọi `A.drop()` có bắt buộc làm B invalid không?

**Đáp án:** Không. Drop hủy membership A. B có thể tiếp tục valid nếu channel còn mở và không có vấn đề lifecycle khác.

### Bài 8 — Close cả kênh

Một DatagramChannel có hai key A và B. Khi `channel.close()` trả về, trạng thái chúng ra sao?

**Đáp án:** Mọi membership của channel bị hủy, A và B invalid. Nếu muốn join lại phải mở channel mới.

### Bài 9 — Đăng ký lại

`key.drop()` rồi `channel.join(group,iface)` thành công. Có nên giữ key cũ để gọi `block`?

**Đáp án:** Không. Key cũ invalid vĩnh viễn. Phải dùng **key mới** do join trả về.

### Bài 10 — Packet sau block

Một source vừa bị block nhưng receive() vẫn thấy gói từ source đó. Có phải chắc chắn Java API hỏng?

**Đáp án:** Không. Gói có thể đã được đệm trước khi block có hiệu lực. Hãy phân loại packet tại app boundary nếu cần chính sách nghiêm ngặt, và test lọc nguồn trên môi trường thực.

### Bài 11 — Packet sau drop

Vừa `drop()` group nhưng còn một datagram group đó đọc ra từ socket. Tại sao?

**Đáp án:** Có thể gói đã nằm trong socket receive buffer. `drop` không phải thao tác xóa buffer hay undo packet đã nhận.

### Bài 12 — So sánh ASM và SSM

Ứng dụng chỉ muốn nhận từ nguồn A, không cần các nguồn khác. Nên tạo ASM rồi chặn hàng nghìn địa chỉ, hay SSM join A?

**Đáp án:** Nếu nền tảng hỗ trợ SSM, dùng `join(group, iface, A)`, tạo key source-specific. ASM + danh sách chặn chỉ loại trừ được các nguồn xác định, không phải allow-list toàn bộ Internet.

### Bài 13 — Join lại ASM

Vẫn còn key ASM hợp lệ cho group/interface, code gọi lại `join(group,iface)`. Có nhất thiết tạo registration mới độc lập không?

**Đáp án:** Không. Theo hợp đồng, nếu đã là member ASM cùng group/interface, Java trả key đại diện membership đang có. Hai component cần thống nhất ownership trước khi drop.

### Bài 14 — Filter không phải firewall

Có thể dùng `key.block(source)` làm hàng rào xác thực duy nhất để chống sender độc hại không?

**Đáp án:** Không. Đây là source filter theo địa chỉ và phụ thuộc OS, gói đã buffered còn có thể tới ứng dụng; nguồn IP có thể bị giả mạo trong một số môi trường. Dữ liệu nhạy cảm cần xác thực/mã hóa theo giao thức.

### Bài 15 — NIC hỗ trợ multicast

`nic.supportsMulticast()==true`, nhưng receiver không nhận packet. Có đủ chứng minh key invalid không?

**Đáp án:** Không. Cần kiểm tra bind/port, group, interface, firewall, IGMP/MLD, TTL/routing, sender và mạng. `key.isValid()` phản ánh lifecycle, không phản ánh phân phối gói end-to-end.

### Bài 16 — Shutdown sạch

Ứng dụng dùng một receiver thread đang `receive`; owner gọi `channel.close()` rồi báo “mọi packet đã xử lý xong”. Sai ở đâu?

**Đáp án:** Đóng channel invalid memberships nhưng không bảo đảm downstream queue/worker đã hoàn thành mọi tác vụ. Cần chờ receiver và hệ thống xử lý kết thúc theo deadline và trạng thái shutdown.

### Bài 17 — Giới hạn output demo

Một máy không có multicast-capable NIC và chương trình in `SKIPPED_NO_MULTICAST_INTERFACE`. Có thể báo đã kiểm thử được block/unblock thật không?

**Đáp án:** Không. Đó là **skip có chủ đích**, tránh false positive. Phải có môi trường hỗ trợ để integration test key thật; có thể unit test state logic tách biệt.

### Bài 18 — Kiểu source

`key.sourceAddress()==null` nhưng code coi điều đó là “receiver chưa join group”. Đúng không?

**Đáp án:** Không. `null` nghĩa key là **ASM (any-source)**. Kiểm tra `key.isValid()` và trạng thái join để xác định membership còn hiệu lực.

### Bài 19 — Source-specific và ASM xung đột

Channel đã join ASM group G trên interface I. Code tiếp tục `join(G,I,sourceA)`. Có chắc luôn thành công?

**Đáp án:** Không. ASM và SSM cùng cặp group/interface có thể xung đột và gây `IllegalStateException`. Phải chọn một mô hình hoặc drop cấu hình cũ rồi join lại theo chính sách.

### Bài 20 — Chọn hoạt động phù hợp

Muốn rời một group nhưng vẫn giữ channel mở phục vụ unicast và group khác. Nên gọi gì?

**Đáp án:** `key.drop()` cho membership đó. Đừng gọi `channel.close()` vì phạm vi rộng hơn yêu cầu.

## 17. Checklist triển khai và kiểm thử

- [ ] Xác định rõ receiver đang dùng **ASM** hay **SSM**.
- [ ] Dùng `DatagramChannel` và `MulticastChannel.join` để nhận membership key thật.
- [ ] Chọn đúng IPv4/IPv6 family với group và source.
- [ ] Chọn `NetworkInterface` đang hoạt động, hỗ trợ multicast và phù hợp route.
- [ ] Bind tới wildcard/port mong muốn, cấu hình reuse trước bind khi cần.
- [ ] Hiểu `MembershipKey.sourceAddress()==null` là ASM, không phải trạng thái chưa join.
- [ ] Dùng `block(source)` chỉ cho ASM key còn valid và OS hỗ trợ.
- [ ] Chỉ dùng source địa chỉ **unicast cùng family** với multicast group.
- [ ] Bắt riêng `IllegalArgumentException`, `IllegalStateException`, `UnsupportedOperationException` và `IOException` ở block.
- [ ] Hiểu block cùng source lặp là no-op, còn unblock không đang blocked thì `IllegalStateException`.
- [ ] Không dùng `supportedOptions` làm bằng chứng source filtering.
- [ ] Không giả định block/drop loại ngay datagram đã buffered.
- [ ] Dùng `drop` để rời một membership mà không đóng các membership khác.
- [ ] Dùng `close` để dừng toàn bộ socket và invalid tất cả keys.
- [ ] Không sử dụng key invalid sau drop/close; rejoin lấy key mới.
- [ ] Tách desired source policy khỏi transient MembershipKey state, áp dụng lại sau restart.
- [ ] Kiểm soát ownership và sự cạnh tranh khi nhiều thread cùng xử lý membership/receive.
- [ ] Nếu cần allow-list một số nguồn, cân nhắc SSM join cho từng nguồn khi OS hỗ trợ.
- [ ] Không biến OS filtering thành biện pháp bảo mật duy nhất.
- [ ] Chạy integration test trên NIC/group/network được phép, không tự gửi packet vào mạng ngoài phạm vi.
- [ ] Nếu không có NIC hỗ trợ, test có thể SKIP, không báo PASS giả.
- [ ] Kiểm thử `join`, source filter supported/unsupported, block/unblock, duplicate unblock, drop/idempotence, rejoin và close.
- [ ] Test riêng packet buffering với sender/receiver kiểm soát nếu nghiệp vụ cần.
- [ ] Đóng channel bằng `try-with-resources` và chờ worker/task shutdown khi cần.
- [ ] Hiểu API lõi Java 7 vẫn hiện hành; ví dụ hoàn chỉnh dùng JDK 17+.

## 18. Tài liệu Java chính thức

- [Java SE 17 — MulticastChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html): `join` theo ASM/SSM, giới hạn OS, yêu cầu network interface và close.
- [Java SE 17 — MembershipKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html): `block`, `unblock`, `drop`, `sourceAddress`, `isValid` và buffered datagram caveat.
- [Java SE 17 — DatagramChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html): UDP receive/send, bind, protocol family và lifecycle.
- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): kiểm tra trạng thái NIC, multicast support và địa chỉ IP.
- [Java SE 17 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_REUSEADDR`, `IP_MULTICAST_IF`, `IP_MULTICAST_TTL` và các socket options liên quan.

## 19. Tổng kết

Trong Java NIO.2, bộ ba **`MembershipKey.block(source)`**, **`MembershipKey.drop()`** và **`DatagramChannel.close()`** giải quyết **ba phạm vi khác nhau**: loại trừ một sender khỏi ASM membership (nếu OS hỗ trợ), hủy một membership cụ thể, và đóng toàn bộ socket cùng mọi membership.

`unblock(source)` chỉ gỡ trạng thái đã block trên key còn valid; nó **không** hồi sinh key sau drop/close. Với yêu cầu chỉ nhận từ một nguồn, mô hình **source-specific multicast** qua `join(group,interface,source)` phù hợp hơn danh sách block source trên ASM, nếu platform có hỗ trợ.

Để code chạy đúng trong thực tế, cần chọn protocol family/interface và bind đúng; phân biệt trạng thái key với khả năng giao gói của mạng; xử lý exception tùy OS; không mặc định datagram đã buffered biến mất ngay sau block/drop; và giữ ownership rõ ràng cho lifecycle của channel/receiver workers. **Đây đều là kiến thức từ Java 7 vẫn còn ứng dụng trong Java hiện đại**, không cần dùng API multicast đã lỗi thời.