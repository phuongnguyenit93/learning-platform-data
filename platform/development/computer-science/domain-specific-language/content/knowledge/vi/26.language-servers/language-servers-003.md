# Đồng bộ tài liệu

Language Server là tiến trình cung cấp các khả năng ngôn ngữ cho editor như phân tích cú pháp, hoàn thành mã, hover, điều hướng đến khai báo, rename và diagnostics. Để những khả năng đó phản ánh đúng nội dung người dùng đang nhìn thấy, client (editor) và server phải duy trì một bản biểu diễn nhất quán của từng tài liệu đang mở. **Đồng bộ tài liệu (document synchronization)** là cơ chế trao đổi những thay đổi của văn bản giữa client và language server, quản lý vòng đời tài liệu, phiên bản nội dung và cách biểu diễn vị trí.

Đồng bộ tài liệu là nền tảng của Language Server Protocol (LSP). Khi người dùng gõ một ký tự, editor cập nhật buffer cục bộ trước rồi gửi thông báo thay đổi cho server. Server áp dụng thay đổi vào bản sao trong bộ nhớ, cập nhật lexer/parser và các chỉ mục liên quan, sau đó trả diagnostics hoặc phục vụ yêu cầu completion, hover và các thao tác khác. Nếu hai phía hiểu khác nhau về phiên bản, offset, newline hoặc thứ tự chỉnh sửa, kết quả có thể trỏ sai vị trí, phân tích nội dung cũ hoặc ghi đè thay đổi chưa lưu.

Một thiết kế tốt cần xác định rõ client và server giữ bản nào, thông báo nào đánh dấu mở/sửa/lưu/đóng, cách truyền thay đổi toàn văn bản hay từng vùng, cách xử lý phiên bản và tác vụ bất đồng bộ, cùng cơ chế khôi phục khi kết nối hoặc trạng thái đồng bộ bị gián đoạn.

## 1. Hai bản tài liệu và nguồn sự thật

Trong editor, tài liệu đang mở thường có một buffer trong bộ nhớ. Buffer này có thể chứa những thay đổi chưa được lưu xuống đĩa. Language server duy trì một bản sao trong bộ nhớ để phân tích và trả kết quả.

Có thể hình dung:

~~~mermaid
flowchart LR
    A[Editor buffer] -->|LSP notifications| B[Language server document store]
    B --> C[Lexer and parser]
    C --> D[AST and semantic model]
    D --> E[Diagnostics and language features]
    E -->|LSP responses/notifications| A
    A -->|Save| F[File on disk]
~~~

Trong lúc tài liệu đang mở, buffer của editor thường là nguồn sự thật cho nội dung hiện tại. Tệp trên đĩa có thể cũ hơn vì người dùng chưa lưu. Server không nên tự đọc lại tệp từ đĩa rồi ghi đè bản trong bộ nhớ bằng nội dung cũ khi nhận yêu cầu completion hoặc diagnostics.

Ví dụ, tệp trên đĩa có:

~~~text
replicas = 2
~~~

Người dùng đổi trong editor thành:

~~~text
replicas = 3
~~~

Trước khi nhấn Save, server phải phân tích giá trị 3 nếu client đã gửi thay đổi. Đọc lại tệp trên đĩa sẽ làm server quay về giá trị 2 và khiến kết quả không khớp với nội dung người dùng nhìn thấy.

Cần phân biệt ba trạng thái:

- **Editor buffer:** nội dung đang hiển thị và có thể chưa lưu.
- **Server document snapshot:** bản nội dung server đã nhận và đang dùng cho phân tích.
- **Disk content:** nội dung đã được ghi xuống hệ thống tệp.

Đồng bộ tài liệu bảo đảm server tiến gần và duy trì nhất quán với buffer theo các thông báo LSP. Việc lưu xuống đĩa là một thao tác riêng.

## 2. Vòng đời tài liệu trong LSP

LSP xác định các thông báo chính để quản lý vòng đời tài liệu:

| Thông báo | Hướng | Ý nghĩa |
|---|---|---|
| textDocument/didOpen | Client → Server | Tài liệu được mở; gửi URI, languageId, version và toàn bộ text |
| textDocument/didChange | Client → Server | Nội dung buffer thay đổi |
| textDocument/willSave | Client → Server | Client sắp lưu tài liệu, nếu tính năng này được hỗ trợ |
| textDocument/willSaveWaitUntil | Client → Server | Client yêu cầu server trả các thay đổi cần áp dụng trước khi lưu, nếu được hỗ trợ |
| textDocument/didSave | Client → Server | Tài liệu đã được lưu |
| textDocument/didClose | Client → Server | Tài liệu được đóng |

Một chu trình đơn giản:

~~~mermaid
sequenceDiagram
    participant E as Editor
    participant L as Language Server
    E->>L: didOpen(uri, version, text)
    E->>L: didChange(uri, version, changes)
    L->>L: Apply changes and analyze
    L-->>E: publishDiagnostics(uri, version, diagnostics)
    E->>L: didSave(uri)
    E->>L: didClose(uri)
    L->>L: Release open-document state
~~~

### 2.1. didOpen

Khi mở tài liệu, client gửi toàn bộ nội dung hiện tại cùng URI, language ID và version. Server tạo document state trong bộ nhớ, khởi tạo line index, lexer/parser hoặc các cấu trúc cần thiết.

Một thông báo minh họa:

~~~json
{
  "jsonrpc": "2.0",
  "method": "textDocument/didOpen",
  "params": {
    "textDocument": {
      "uri": "file:///workspace/app.dsl",
      "languageId": "mydsl",
      "version": 1,
      "text": "service \"catalog\" {}"
    }
  }
}
~~~

Server nên xử lý mở lặp lại theo đúng vòng đời client và quy tắc LSP. Một URI đang mở thường tương ứng với một document state đang hoạt động. Nếu nhận trạng thái không hợp lệ, cần ghi log và phục hồi có kiểm soát thay vì tạo nhiều bản sao không liên kết.

### 2.2. didChange

Khi buffer thay đổi, client gửi thông báo didChange. Nội dung có thể là toàn bộ văn bản mới hoặc một hay nhiều edit theo vùng, tùy khả năng đồng bộ đã thương lượng khi khởi tạo.

Server phải áp dụng các thay đổi theo đúng thứ tự và cập nhật version. Sau đó, nó có thể lên lịch phân tích lại và cập nhật diagnostics.

### 2.3. didSave

didSave thông báo tài liệu đã được lưu. Nếu client và server đã thương lượng capability phù hợp, thông báo có thể kèm toàn bộ nội dung. Server có thể dùng sự kiện này để chạy kiểm tra tốn kém, ghi cache hoặc đồng bộ trạng thái với công cụ build.

Không nên giả định didSave luôn có nội dung văn bản. Hành vi phụ thuộc capability và cách client gửi thông báo.

### 2.4. didClose

Khi tài liệu đóng, server giải phóng trạng thái buffer đang mở, hủy tác vụ phân tích không còn cần thiết và xóa cache gắn với phiên mở nếu phù hợp. Tài liệu vẫn có thể tồn tại trên đĩa; didClose không có nghĩa là xóa tệp.

Nếu server giữ workspace index hoặc cache toàn dự án, nó có thể tiếp tục giữ mô hình đã phân tích ở mức workspace. Cần phân biệt cache dự án với trạng thái buffer của một tài liệu đang mở.

## 3. Thương lượng chế độ đồng bộ

Client công bố capability và server công bố khả năng đồng bộ trong kết quả initialize. Một phần capability của server là text document synchronization.

LSP hỗ trợ các chế độ chính:

| Chế độ | Giá trị khái niệm | Hành vi |
|---|---|---|
| None | Không đồng bộ thay đổi văn bản | Server không nhận didChange theo cơ chế này |
| Full | Toàn bộ nội dung | Mỗi lần thay đổi gửi toàn văn bản hiện tại |
| Incremental | Thay đổi theo vùng | Gửi các đoạn văn bản được chèn, xóa hoặc thay thế |

Server cũng có thể khai báo có nhận open/close và save notification hay không. Client cần tuân theo capability đã thương lượng, không tự giả định server hỗ trợ mọi kiểu thông báo.

### 3.1. Full synchronization

Ở chế độ Full, mỗi didChange mang toàn bộ nội dung buffer mới. Cách này đơn giản: server thay văn bản hiện tại bằng văn bản nhận được.

Ưu điểm:

- Logic áp dụng thay đổi dễ triển khai.
- Ít rủi ro sai offset khi xử lý nhiều edit nhỏ.
- Phục hồi trạng thái tương đối dễ vì mỗi thông báo là một snapshot đầy đủ.
- Phù hợp với DSL nhỏ hoặc tài liệu không thường xuyên thay đổi.

Hạn chế:

- Mỗi lần gõ có thể truyền toàn bộ tệp.
- Tốn băng thông với tài liệu lớn.
- Server phải giải mã và cập nhật nhiều nội dung không thay đổi.
- Có thể tạo áp lực cấp phát bộ nhớ và phân tích lặp lại.

Full sync là lựa chọn hợp lý khi tính đơn giản quan trọng hơn chi phí truyền dữ liệu, hoặc khi tài liệu nhỏ. Nó không nhất thiết có nghĩa server phải parse toàn bộ từ đầu cho mọi lần thay đổi; server vẫn có thể so sánh snapshot và dùng phân tích gia tăng nội bộ.

### 3.2. Incremental synchronization

Ở chế độ Incremental, client gửi một danh sách thay đổi gồm range và text mới. Server áp dụng edit vào snapshot hiện tại.

Ví dụ, người dùng thay số 2 thành số 3:

~~~json
{
  "textDocument": {
    "uri": "file:///workspace/app.dsl",
    "version": 7
  },
  "contentChanges": [
    {
      "range": {
        "start": { "line": 1, "character": 14 },
        "end": { "line": 1, "character": 15 }
      },
      "text": "3"
    }
  ]
}
~~~

Range có điểm bắt đầu được tính bao gồm và điểm kết thúc không bao gồm. Tọa độ line và character dùng quy ước của LSP và position encoding đã thương lượng.

Ưu điểm:

- Chỉ truyền phần thay đổi.
- Giảm dữ liệu qua giao thức khi người dùng sửa ít ký tự.
- Có thể tận dụng để cập nhật line index, token và cây cú pháp theo vùng.

Hạn chế:

- Server phải áp dụng range chính xác.
- Sai position encoding hoặc line index sẽ làm hỏng toàn bộ edit tiếp theo.
- Các thay đổi trong cùng một thông báo cần được áp dụng đúng thứ tự.
- Khó phục hồi nếu server mất một thông báo incremental.

Với tài liệu lớn và editor tương tác, incremental sync thường hữu ích. Nhưng nó đòi hỏi quản lý version và vị trí nghiêm ngặt.

## 4. Cấu trúc contentChanges

Một didChange chứa một danh sách contentChanges. Mỗi phần tử có thể biểu diễn toàn bộ văn bản hoặc một edit theo vùng.

Edit theo vùng thường có:

- **range.start:** vị trí bắt đầu.
- **range.end:** vị trí kết thúc.
- **text:** nội dung thay thế.

Nếu range không được cung cấp, phần tử biểu diễn thay đổi toàn bộ tài liệu. Client và server phải tuân theo dạng đã thương lượng.

Ví dụ thay một thuộc tính:

~~~text
replicas = 2
port = 8080
~~~

Người dùng sửa thành:

~~~text
replicas = 3
port = 8080
~~~

Một edit có thể chỉ thay ký tự số. Server giữ nguyên phần văn bản còn lại và thay đúng range.

### 4.1. Thứ tự áp dụng nhiều edit

Các edit trong contentChanges được áp dụng theo thứ tự xuất hiện trong mảng. Mỗi edit tiếp theo được tính trên trạng thái văn bản sau khi các edit trước đó đã được áp dụng.

Ví dụ, edit thứ nhất chèn một dòng ở đầu tài liệu. Edit thứ hai có range theo nội dung sau lần chèn đó, không phải luôn theo snapshot ban đầu. Server không nên gom mọi range rồi áp dụng đồng thời trên một phiên bản văn bản cũ trừ khi nó có phép chuyển đổi tọa độ đúng.

### 4.2. Edit toàn văn bản xen với edit theo vùng

Nếu một phần tử không có range, nó thay thế toàn bộ nội dung tại thời điểm phần tử đó được áp dụng. Các phần tử tiếp theo, nếu có, phải được áp dụng trên văn bản mới này.

Client thông thường không cần trộn nhiều cách biểu diễn trong một thông báo nếu không có lý do. Server vẫn cần xử lý theo đặc tả và không được giả định mọi phần tử đều có range.

### 4.3. Không áp dụng edit theo thứ tự ngược tùy tiện

Một số API chỉnh sửa nội bộ có quy tắc áp dụng edit theo offset giảm dần để tránh dịch chuyển vị trí. Đó là một chiến lược khác với cách LSP yêu cầu áp dụng danh sách contentChanges theo thứ tự. Nếu chuyển các edit LSP sang một batch API nội bộ, adapter phải chuyển đổi thứ tự và tọa độ một cách đúng đắn.

## 5. Version của tài liệu

Mỗi tài liệu đang mở có version do client quản lý và gửi trong didOpen/didChange. Version là số nguyên được dùng để phân biệt các trạng thái nội dung theo thời gian.

Ví dụ:

| Sự kiện | Version | Nội dung |
|---|---:|---|
| didOpen | 1 | Tài liệu ban đầu |
| didChange | 2 | Sửa tên service |
| didChange | 3 | Thêm thuộc tính replicas |
| didChange | 4 | Sửa giá trị replicas |
| didSave | Có thể không mang version mới | Báo đã lưu trạng thái hiện tại |

Version thường tăng khi nội dung thay đổi. Server nên lưu version cùng snapshot và dùng nó để nhận diện kết quả cũ hoặc thông báo đến muộn.

### 5.1. Version không phải timestamp

Không nên xem version là thời gian thực hoặc dùng nó để so sánh giữa các tài liệu khác nhau. Version thuộc về một tài liệu và một vòng đời mở cụ thể. Nó có thể bắt đầu từ một giá trị tùy ý và chỉ có ý nghĩa theo thứ tự client gửi.

### 5.2. Bỏ qua kết quả cũ

Giả sử server bắt đầu phân tích version 10. Trước khi hoàn tất, client gửi version 11. Phân tích version 10 có thể kết thúc sau version 11. Nếu server công bố diagnostics cũ sau kết quả mới, editor sẽ hiển thị lỗi không còn tồn tại.

Trước khi công bố kết quả, server cần so sánh version của snapshot đã phân tích với version hiện tại. Nếu không còn khớp, bỏ kết quả cũ hoặc chỉ dùng nó cho cache không ảnh hưởng giao diện.

### 5.3. Version không hợp lệ hoặc bị lặp

Nếu nhận version thấp hơn trạng thái hiện tại, server cần tránh áp dụng một cách mù quáng. Tùy vòng đời và client, đây có thể là thông báo đến muộn, trạng thái khởi động lại hoặc lỗi đồng bộ. Server nên ghi nhận bất thường, bỏ dữ liệu stale khi phù hợp và yêu cầu đồng bộ lại nếu không thể tin cậy trạng thái hiện tại.

Không nên tự tăng version thay client. Server lưu version được gửi và dùng nó để gắn kết quả với snapshot tương ứng.

## 6. Position encoding và tọa độ văn bản

LSP biểu diễn vị trí bằng line và character. Cả hai là số nguyên bắt đầu từ 0. Line 0 là dòng đầu tiên; character 0 là vị trí đầu dòng.

Đơn vị của character phụ thuộc position encoding. Trong LSP hiện đại, client và server có thể thương lượng encoding như UTF-8, UTF-16 hoặc UTF-32. Nếu không thương lượng encoding khác, UTF-16 là giá trị mặc định theo quy tắc LSP.

Đây là điểm quan trọng với Unicode. Một ký tự nhìn thấy không nhất thiết tương ứng với một đơn vị UTF-16 hoặc UTF-8.

Ví dụ, chuỗi:

~~~text
A😀B
~~~

Có ba Unicode code point, nhưng ký tự emoji nằm ngoài BMP nên chiếm hai UTF-16 code unit và bốn byte UTF-8. Vị trí của B vì thế khác nhau tùy encoding:

| Encoding | Character index của B |
|---|---:|
| UTF-8 | 5 byte |
| UTF-16 | 3 code unit |
| UTF-32 | 2 code point |

Ví dụ trên đếm từ đầu dòng và không tính newline. Server phải dùng đúng encoding đã thương lượng khi chuyển line/character thành offset nội bộ.

### 6.1. Không trộn offset nội bộ với LSP character

Java String thường dùng UTF-16 code unit làm chỉ số. Điều này thuận tiện nếu server chọn UTF-16. Nếu server dùng UTF-8 hoặc UTF-32, cần chuyển đổi giữa character index của LSP và offset của chuỗi nội bộ.

Không nên dùng trực tiếp một con số LSP làm offset byte hoặc index Java String khi encoding không khớp.

### 6.2. Range nửa mở

Một range LSP gồm start và end. Start được tính vào vùng; end nằm ngay sau vùng. Range rỗng có start bằng end, thường dùng để chèn văn bản.

Ví dụ, thay từ ký tự thứ 4 đến ngay trước ký tự thứ 7 nghĩa là ba đơn vị vị trí theo encoding đã chọn sẽ bị thay thế. Cần nhớ character ở đây không nhất thiết là grapheme cluster mà người dùng nhìn thấy.

### 6.3. Line ending

Server cần xử lý LF, CRLF và các quy ước newline khác mà parser hỗ trợ. Line/character của LSP được tính theo dòng văn bản, không nên tính CR và LF của cùng một CRLF thành hai dòng. Khi xây line index, cần ghi nhận ranh giới dòng theo cách nhất quán với văn bản buffer.

## 7. Chuyển LSP position thành offset

Parser thường thao tác trên offset tuyến tính, trong khi LSP gửi line/character. Server cần một line index để chuyển đổi.

Một cấu trúc đơn giản có thể lưu offset bắt đầu của từng dòng:

~~~java
record LineIndex(int[] lineStartOffsets) {
    int toOffset(String text, int line, int character) {
        if (line < 0 || line >= lineStartOffsets.length) {
            throw new IllegalArgumentException("Invalid line");
        }

        int start = lineStartOffsets[line];
        int end = line + 1 < lineStartOffsets.length
            ? lineStartOffsets[line + 1]
            : text.length();

        int offset = start + character;
        if (offset > end) {
            throw new IllegalArgumentException("Invalid character");
        }
        return offset;
    }
}
~~~

Đây là ví dụ giản lược cho trường hợp character và offset cùng đơn vị UTF-16. Một implementation đầy đủ phải:

- Dùng position encoding đã thương lượng.
- Loại trừ ký tự newline khỏi giới hạn character của dòng theo quy tắc vị trí.
- Xử lý CRLF.
- Xử lý surrogate pair nếu dùng UTF-16.
- Từ chối hoặc clamp range không hợp lệ theo policy đã chọn.
- Cập nhật line index sau mỗi edit.
- Tránh chuyển đổi lặp lại toàn bộ văn bản nếu tài liệu lớn.

Một line index có thể dùng mảng offset cho tài liệu nhỏ. Với tài liệu lớn và nhiều edit, có thể dùng cấu trúc dữ liệu hỗ trợ cập nhật theo vùng như rope, piece table hoặc balanced tree.

## 8. Áp dụng incremental edit chính xác

Server có thể lưu document text cùng line index và version. Khi nhận một edit:

1. Xác nhận URI đang có document state.
2. Kiểm tra version mới theo chính sách.
3. Chuyển range từ LSP position sang offset.
4. Xác nhận start không vượt end và nằm trong giới hạn.
5. Thay đoạn văn bản bằng text mới.
6. Cập nhật line index và version.
7. Đánh dấu vùng phân tích bị ảnh hưởng.
8. Lên lịch cập nhật diagnostics và semantic model.

Pseudocode:

~~~java
void applyChange(
        OpenDocument document,
        int newVersion,
        List<ContentChange> changes) {

    if (newVersion <= document.version()) {
        handleStaleChange(document, newVersion);
        return;
    }

    String text = document.text();
    LineIndex index = document.lineIndex();

    for (ContentChange change : changes) {
        if (change.range() == null) {
            text = change.text();
            index = LineIndex.build(text);
        } else {
            int start = index.toOffset(text, change.range().start());
            int end = index.toOffset(text, change.range().end());

            if (start > end) {
                throw new InvalidEditException();
            }

            text = text.substring(0, start)
                + change.text()
                + text.substring(end);

            index = LineIndex.build(text);
        }
    }

    document.replaceSnapshot(text, index, newVersion);
}
~~~

Đây là pseudocode minh họa; một server thực tế cần đồng bộ thread, xử lý encoding và tránh dựng lại toàn bộ line index sau mỗi edit nếu chi phí quá lớn.

### 8.1. Kiểm tra range

Range sai có thể xuất hiện do lỗi client, sai position encoding, trạng thái server đã lệch hoặc lỗi triển khai. Server không nên âm thầm cắt range vào giới hạn văn bản nếu điều đó có thể làm nội dung sai. Cần ghi log, từ chối edit không thể áp dụng và có cơ chế yêu cầu đồng bộ lại hoặc tái mở tài liệu.

### 8.2. Thay đổi nhiều dòng

Một edit có thể xóa nhiều dòng rồi chèn một đoạn mới chứa newline. Line index phải cập nhật cả số dòng và offset của các dòng phía sau. Nếu chỉ điều chỉnh cột hiện tại mà không cập nhật dòng, các edit tiếp theo sẽ bị lệch.

## 9. Đồng bộ với parser và semantic model

Sau khi server cập nhật text snapshot, các cấu trúc phân tích cần được cập nhật theo snapshot đó:

- Token stream hoặc lexer state.
- CST/AST.
- Symbol table.
- Reference index.
- Type information.
- Diagnostics.
- Cache completion và hover.
- Source map hoặc các liên kết vị trí nếu DSL có sinh mã.

Không phải mọi thay đổi đều cần phân tích lại toàn bộ dự án. Một edit trong literal có thể chỉ ảnh hưởng một biểu thức; đổi tên khai báo có thể ảnh hưởng mọi tham chiếu trong module hoặc workspace.

Server có thể bắt đầu với full reparse để đơn giản và chính xác. Khi hiệu năng yêu cầu, nó có thể dùng incremental parsing và dependency tracking. Dù dùng cách nào, kết quả phải gắn với version của document snapshot mà nó được tạo từ đó.

## 10. Đồng bộ và xử lý bất đồng bộ

Language server thường xử lý nhiều request đồng thời. Completion, hover, diagnostics và indexing có thể chạy trên các executor khác nhau. Nếu không gắn snapshot/version, một request có thể đọc một phần trạng thái cũ và một phần trạng thái mới.

Ví dụ:

1. Request hover bắt đầu ở version 20.
2. Người dùng sửa tài liệu; server nhận version 21.
3. Parser tạo AST version 21.
4. Hover cũ tiếp tục đọc symbol table mới nhưng offset từ văn bản version 20.
5. Kết quả có thể trỏ nhầm symbol hoặc range.

Một cách thiết kế là tạo immutable document snapshot:

~~~java
record DocumentSnapshot(
    String uri,
    int version,
    String text,
    SyntaxTree syntaxTree,
    SemanticModel semanticModel
) {}
~~~

Mỗi request lấy một snapshot nhất quán tại thời điểm bắt đầu. Nếu snapshot chưa có AST mới nhất, server có thể đợi phân tích, dùng kết quả gần nhất theo policy hoặc trả kết quả rỗng/partial phù hợp. Không nên trộn dữ liệu từ nhiều revision.

### 10.1. Hủy tác vụ cũ

Khi tài liệu thay đổi, tác vụ phân tích cũ có thể không còn cần thiết. Server có thể dùng cancellation token hoặc generation ID để dừng công việc tốn kém. Tuy nhiên, hủy tác vụ cần được thực hiện hợp tác; một tác vụ đang chạy phải kiểm tra cancellation ở các điểm phù hợp.

### 10.2. Kiểm tra version trước khi publish

Trước khi gửi publishDiagnostics, server nên xác nhận kết quả vẫn thuộc version hiện tại. Nếu không, bỏ kết quả stale. Tương tự, cache completion hoặc semantic token cần được gắn với document version hoặc invalidation key phù hợp.

### 10.3. Debounce và throttle

Không nhất thiết phải parse lại sau từng ký tự ngay lập tức. Server có thể debounce diagnostics trong một khoảng ngắn để gộp các thay đổi liên tiếp. Nhưng completion hoặc hover cần phản hồi nhanh hơn và có thể dùng snapshot mới nhất ngay khi nhận được.

Debounce không được làm mất edit. Mọi didChange vẫn phải được áp dụng theo thứ tự; chỉ việc phân tích hoặc publish kết quả mới có thể được gộp.

## 11. Diagnostics gắn với phiên bản tài liệu

Server thường gửi diagnostics bằng notification publishDiagnostics. Kết quả có thể chứa URI, version và danh sách lỗi/cảnh báo.

Ví dụ:

~~~json
{
  "jsonrpc": "2.0",
  "method": "textDocument/publishDiagnostics",
  "params": {
    "uri": "file:///workspace/app.dsl",
    "version": 12,
    "diagnostics": [
      {
        "range": {
          "start": { "line": 3, "character": 4 },
          "end": { "line": 3, "character": 12 }
        },
        "severity": 1,
        "message": "Unknown service reference"
      }
    ]
  }
}
~~~

Version giúp client nhận biết diagnostics thuộc nội dung nào. Nếu server phát kết quả của version cũ sau khi editor đã có version mới, client có thể bỏ qua hoặc hiển thị không đúng. Server vẫn nên tránh gửi kết quả stale thay vì phụ thuộc hoàn toàn vào client.

Khi lỗi được sửa, server cần publish danh sách diagnostics mới, kể cả danh sách rỗng, để xóa lỗi cũ. Khi tài liệu đóng, client thường loại bỏ diagnostics gắn với buffer đó; server nên tuân theo hành vi LSP và không tiếp tục phát kết quả cho phiên tài liệu đã đóng.

## 12. Đồng bộ tài liệu đang mở với file system

LSP có thêm các cơ chế liên quan đến thay đổi file trong workspace, chẳng hạn watched files. Chúng không thay thế didChange của tài liệu đang mở.

Cần phân biệt:

- **didChange:** buffer trong editor thay đổi.
- **didSave:** buffer được lưu.
- **workspace/didChangeWatchedFiles:** file system báo tệp được tạo, sửa hoặc xóa.
- **workspace/didChangeWorkspaceFolders:** tập thư mục workspace thay đổi.

Một file watcher có thể báo một tệp thay đổi do Git checkout, build tool hoặc editor khác. Nếu URI đó đang mở trong editor, server phải quyết định cách phối hợp với buffer chưa lưu.

Không nên để file watcher ghi đè nội dung buffer đang mở. Có thể cập nhật disk snapshot riêng, đánh dấu xung đột hoặc dùng thay đổi đó để làm mới workspace index. Buffer hiện tại vẫn cần được đồng bộ theo thông báo của client.

## 13. Tài liệu chưa lưu và thay đổi bên ngoài

Một trường hợp phức tạp:

1. Người dùng mở file và sửa nhưng chưa lưu.
2. Một tiến trình bên ngoài sửa cùng file trên đĩa.
3. File watcher báo thay đổi.
4. Buffer editor vẫn chứa nội dung riêng.

Server cần giữ rõ hai revision: nội dung editor và nội dung disk. Tùy tính năng, server có thể:

- Dùng buffer editor cho language features của tài liệu đang mở.
- Cập nhật workspace index từ file khác không mở.
- Gửi thông tin hoặc diagnostics về xung đột nếu ứng dụng hỗ trợ.
- Chờ editor xử lý reload/merge và gửi didChange tương ứng.
- Tránh tự chọn một phiên bản rồi ghi đè phiên bản còn lại.

Đây là vấn đề đồng bộ trạng thái, không chỉ là đọc lại file. Cần tránh cập nhật âm thầm vì có thể làm mất thay đổi chưa lưu.

## 14. URI và định danh tài liệu

LSP dùng URI để định danh tài liệu. Với tệp cục bộ, URI thường có dạng file URI; tài liệu ảo có thể dùng scheme riêng như untitled hoặc scheme do extension cung cấp.

Server cần dùng URI một cách nhất quán:

- Chuẩn hóa URI theo quy tắc phù hợp.
- Không tự chuyển URI thành đường dẫn bằng cách cắt chuỗi.
- Xử lý percent encoding.
- Phân biệt chữ hoa/chữ thường theo quy tắc URI và filesystem.
- Không giả định mọi tài liệu đều là file cục bộ.
- Giữ scheme và authority khi định danh.
- Xử lý rename/move theo thông báo hoặc cơ chế workspace phù hợp.

Hai URI có thể trỏ đến cùng một file theo cách biểu diễn khác nhau. Nếu server không chuẩn hóa phù hợp, nó có thể tạo hai document state cho cùng một tài liệu. Ngược lại, chuẩn hóa quá mạnh có thể gộp nhầm URI vốn khác nhau trên filesystem phân biệt case hoặc trên remote workspace.

## 15. Khởi động lại server và khôi phục đồng bộ

Language server có thể bị crash, được restart sau khi đổi cấu hình hoặc được client khởi động lại. Server mới thường không có document state trong bộ nhớ.

Client cần gửi lại trạng thái mở theo lifecycle phù hợp, bao gồm didOpen với toàn bộ nội dung hiện tại. Không nên kỳ vọng server có thể khôi phục buffer chưa lưu chỉ bằng cách đọc file trên đĩa.

Khi khởi động lại:

1. Client initialize lại và thương lượng capability.
2. Client thông báo các tài liệu đang mở theo trạng thái hiện tại.
3. Server tạo snapshot mới từ nội dung client gửi.
4. Server khởi tạo phân tích và diagnostics.
5. Các request tiếp theo dùng snapshot mới.

Nếu server có cache bền vững, cache đó chỉ là dữ liệu tăng tốc. Nó cần được xác nhận theo URI, version hoặc content hash; không được thay thế nội dung buffer mới mà client gửi.

## 16. Đồng bộ workspace và nhiều tài liệu

Một DSL có thể có nhiều module liên kết với nhau. Mỗi tài liệu có version riêng, nhưng semantic model của workspace có thể phụ thuộc vào nhiều tài liệu.

Ví dụ:

~~~text
# services.dsl
service "catalog" {}
~~~

~~~text
# deployment.dsl
deploy "main" {
    target = "catalog"
}
~~~

Khi services.dsl thay đổi, diagnostics của deployment.dsl có thể cần được cập nhật vì tham chiếu hoặc kiểu của service đã đổi.

Server cần phân biệt:

- Version riêng của từng document.
- Revision hoặc generation của workspace index.
- Snapshot của dependency graph.
- Kết quả phân tích phụ thuộc nhiều tài liệu.

Có thể dùng workspace generation ID để gắn một lượt indexing với tập revision cụ thể. Khi một tài liệu thay đổi, server đánh dấu các phụ thuộc bị ảnh hưởng và lên lịch cập nhật. Kết quả chỉ được publish nếu vẫn phù hợp với trạng thái workspace hiện tại.

## 17. Đồng bộ và các tính năng ngôn ngữ

Nhiều tính năng LSP phụ thuộc vào nội dung đúng version:

| Tính năng | Dữ liệu cần đồng bộ |
|---|---|
| Completion | Buffer, vị trí con trỏ, AST và symbol index |
| Hover | Token tại vị trí và semantic model |
| Go to definition | Tham chiếu và symbol table |
| Find references | Chỉ mục tham chiếu theo workspace revision |
| Rename | Symbol identity và vị trí mọi occurrence |
| Formatting | Snapshot nguồn và quy tắc formatter |
| Semantic tokens | Token classification theo document version |
| Code actions | Diagnostics và source ranges hiện tại |
| Inlay hints | Kiểu, giá trị suy ra và vị trí hiện tại |
| Diagnostics | Parser/semantic result của snapshot tương ứng |

Một request thường chỉ mang URI và position, không nhất thiết mang version tường minh như didChange. Server phải xử lý request trên snapshot nhất quán mà nó có tại thời điểm xử lý. Nếu request đến ngay sau didChange trên cùng kết nối, thứ tự thông điệp LSP là cơ sở để server cập nhật trạng thái trước khi xử lý request; kiến trúc bất đồng bộ bên trong vẫn phải giữ đúng thứ tự và snapshot.

## 18. Hiệu năng của đồng bộ tài liệu

Với tài liệu nhỏ, lưu một String và parse lại toàn bộ có thể đủ đơn giản. Với tài liệu lớn hoặc thay đổi liên tục, cần tối ưu có đo lường.

Các kỹ thuật có thể dùng:

- Incremental sync để giảm payload.
- Line index cập nhật theo vùng.
- Rope hoặc piece table để chỉnh sửa văn bản hiệu quả.
- Incremental lexer/parser để tái sử dụng phần không đổi.
- Debounce diagnostics và semantic analysis.
- Hủy tác vụ phân tích cũ.
- Cache theo version hoặc content hash.
- Chỉ cập nhật dependency graph bị ảnh hưởng.
- Giới hạn số diagnostics hoặc chi phí phân tích cho buffer lỗi nặng.

Không nên thêm incremental parsing quá sớm nếu full parse vẫn đáp ứng độ trễ. Nhưng ngay cả khi parse lại toàn bộ, server vẫn cần incremental document synchronization chính xác nếu client đã thương lượng chế độ đó.

## 19. Xử lý lỗi đồng bộ và phục hồi

Một server cần có chính sách cho các trường hợp bất thường:

| Tình huống | Rủi ro | Hành động phù hợp |
|---|---|---|
| didChange đến khi chưa didOpen | Không có snapshot nền | Ghi log, bỏ hoặc yêu cầu lifecycle được khôi phục |
| Version cũ | Áp dụng edit lên snapshot mới hơn | Bỏ stale change và đồng bộ lại nếu cần |
| Range vượt giới hạn | Cắt sai văn bản | Từ chối edit, ghi log và phục hồi snapshot |
| Position encoding không khớp | Lệch offset sau Unicode | Kiểm tra negotiation và chuyển đổi đúng |
| Bỏ lỡ một edit | Server lệch buffer | Yêu cầu client gửi full text hoặc tái mở tài liệu |
| Tác vụ parse cũ hoàn tất muộn | Diagnostics stale | Kiểm tra version trước khi publish |
| didClose khi tác vụ đang chạy | Kết quả cho tài liệu đã đóng | Hủy hoặc bỏ kết quả |
| Server restart | Mất buffer trong bộ nhớ | Client gửi didOpen với text hiện tại |
| File watcher báo thay đổi | Xung đột với unsaved buffer | Giữ buffer editor và quản lý disk snapshot riêng |

LSP notification không có response riêng như request. Vì vậy, server cần logging, telemetry và cơ chế phục hồi để phát hiện trạng thái không nhất quán. Nếu server không thể xác định nội dung hiện tại, việc nhận lại toàn văn bản từ client là cách khôi phục đáng tin cậy hơn việc tự đoán các edit đã mất.

## 20. Thiết kế DocumentStore trong server

Một DocumentStore có thể quản lý trạng thái từng URI:

~~~java
record OpenDocument(
    String uri,
    String languageId,
    int version,
    String text,
    LineIndex lineIndex
) {}

interface DocumentStore {
    Optional<OpenDocument> get(String uri);
    void open(OpenDocument document);
    void applyChanges(String uri, int version, List<ContentChange> changes);
    void close(String uri);
}
~~~

Trong hệ thống thực tế, snapshot nên bất biến hoặc được thay thế nguyên tử sau khi áp dụng xong toàn bộ thông báo. Request đang chạy có thể giữ tham chiếu đến snapshot cũ mà không bị sửa giữa chừng.

DocumentStore cần xử lý thread safety. Có thể dùng lock theo URI, actor/mailbox riêng cho từng tài liệu hoặc một hàng đợi tuần tự. Mục tiêu là hai didChange của cùng một tài liệu không áp dụng đồng thời theo thứ tự sai, trong khi tài liệu khác vẫn có thể được xử lý song song.

## 21. Quy tắc phối hợp giữa document store và workspace index

DocumentStore giữ buffer của tài liệu đang mở. Workspace index thường giữ thông tin toàn dự án như symbol, module và tham chiếu. Hai thành phần có vòng đời khác nhau.

Một thay đổi trong buffer có thể:

1. Cập nhật DocumentStore ngay.
2. Đánh dấu document version mới.
3. Phân tích tài liệu và tạo AST.
4. Cập nhật workspace index nếu AST đủ ổn định.
5. Đánh dấu các tài liệu phụ thuộc cần kiểm tra lại.
6. Publish diagnostics khi kết quả phù hợp với revision hiện tại.

Không nên cập nhật workspace index bằng một AST cũ sau khi AST mới hơn đã được công bố. Có thể gắn mỗi index update với document version và workspace generation để từ chối kết quả đến muộn.

## 22. Ví dụ xử lý một chuỗi thay đổi

Giả sử tài liệu ban đầu:

~~~text
service "catalog" {
    replicas = 2
}
~~~

Client mở tài liệu với version 1. Người dùng đổi số 2 thành 3, sau đó thêm một thuộc tính port.

Một chuỗi thông báo có thể là:

~~~text
didOpen(version=1, full text)
didChange(version=2, replace "2" with "3")
didChange(version=3, insert "    port = 8080\n" before closing brace)
didSave
~~~

Server thực hiện:

1. Tạo snapshot version 1.
2. Áp dụng edit version 2 lên snapshot 1.
3. Áp dụng edit version 3 lên snapshot 2.
4. Lên lịch phân tích snapshot version 3.
5. Publish diagnostics cho version 3 nếu kết quả vẫn còn hiện hành.
6. Nhận didSave và cập nhật trạng thái lưu nếu cần.

Nếu phân tích version 2 kết thúc sau version 3, kết quả version 2 phải bị bỏ qua. Nếu người dùng đóng tài liệu trước khi phân tích version 3 hoàn tất, server không nên publish diagnostics cho document state đã đóng.

## 23. Kiểm thử document synchronization

Kiểm thử cần xác nhận cả văn bản cuối cùng lẫn trạng thái phiên bản và kết quả ngôn ngữ.

### 23.1. Kiểm thử lifecycle

- didOpen tạo document state đúng URI và text.
- didChange cập nhật nội dung và version.
- didSave được xử lý dù không có text kèm theo.
- didClose giải phóng trạng thái mở.
- Mở lại tài liệu tạo snapshot từ nội dung client gửi.

### 23.2. Kiểm thử full và incremental sync

- Full change thay thế toàn bộ nội dung.
- Incremental change thay đúng range.
- Nhiều change trong một thông báo được áp dụng theo thứ tự.
- Insert, delete và replace hoạt động đúng.
- Range rỗng chèn văn bản đúng vị trí.
- Thay đổi nhiều dòng cập nhật line index.

### 23.3. Kiểm thử Unicode và newline

- ASCII.
- Ký tự ngoài BMP.
- Combining marks.
- Tab.
- LF và CRLF.
- Vị trí ở cuối dòng và EOF.
- Chuyển đổi UTF-8/UTF-16/UTF-32 theo encoding đã thương lượng.

### 23.4. Kiểm thử version và concurrency

- Version tăng liên tiếp.
- Thông báo stale.
- Parse version cũ hoàn tất muộn.
- didClose trong khi parse đang chạy.
- Hai tài liệu thay đổi đồng thời.
- Request hover/completion cùng lúc với didChange.
- Server restart và client mở lại tài liệu.

### 23.5. Kiểm thử đồng bộ file system

- File watcher báo file không mở thay đổi.
- File watcher báo file đang mở thay đổi bên ngoài.
- Buffer chưa lưu không bị ghi đè.
- Workspace folder được thêm hoặc bỏ.
- URI có percent encoding hoặc scheme không phải file.

## 24. Quy trình triển khai document synchronization

Có thể triển khai theo trình tự:

1. **Thương lượng capability:** đọc client capabilities và công bố chế độ đồng bộ server hỗ trợ.
2. **Tạo DocumentStore:** lưu URI, language ID, version, text và line index.
3. **Xử lý didOpen:** tạo snapshot từ toàn bộ nội dung client gửi.
4. **Xử lý didChange:** áp dụng full hoặc incremental change đúng thứ tự.
5. **Chuyển đổi position:** dùng position encoding đã thương lượng.
6. **Cập nhật snapshot nguyên tử:** không để request đọc trạng thái nửa cũ nửa mới.
7. **Lên lịch phân tích:** gắn AST, semantic model và diagnostics với version.
8. **Bỏ kết quả stale:** kiểm tra version trước khi publish hoặc cập nhật index.
9. **Xử lý save/close:** cập nhật trạng thái lưu và giải phóng buffer khi đóng.
10. **Phối hợp file watcher:** tách disk changes khỏi buffer changes.
11. **Khôi phục trạng thái:** nhận lại full text sau restart hoặc khi mất đồng bộ.
12. **Kiểm thử concurrency và Unicode:** xác nhận vị trí và thứ tự edit chính xác.

## 25. Nguyên tắc thiết kế

- **Buffer editor là nguồn nội dung đang mở:** không thay nó bằng dữ liệu cũ trên đĩa.
- **Tuân thủ capability đã thương lượng:** chỉ dùng chế độ full/incremental mà hai bên hỗ trợ.
- **Áp dụng edit theo đúng thứ tự:** các range tiếp theo được hiểu trên trạng thái sau edit trước.
- **Version gắn với snapshot:** không dùng kết quả phân tích cũ cho tài liệu mới.
- **Dùng đúng position encoding:** UTF-8, UTF-16 hoặc UTF-32 phải được chuyển đổi nhất quán.
- **Range nửa mở và line index rõ ràng:** tránh lệch vị trí ở cuối dòng, newline và Unicode.
- **Snapshot nhất quán cho request:** không trộn AST, text và symbol table của các revision khác nhau.
- **Hủy hoặc bỏ tác vụ cũ:** ngăn diagnostics và cache stale.
- **Tách buffer khỏi disk state:** file watcher không được ghi đè thay đổi chưa lưu.
- **Quản lý URI đúng chuẩn:** hỗ trợ file và tài liệu ảo mà không tạo document state trùng.
- **Khôi phục bằng snapshot đầy đủ:** khi mất một incremental edit, không đoán nội dung.
- **Kiểm thử lifecycle, concurrency và trường hợp biên:** đồng bộ đúng là điều kiện nền cho mọi language feature.

Đồng bộ tài liệu giữ cho language server phân tích đúng nội dung mà người dùng đang chỉnh sửa. Khi lifecycle open/change/save/close được quản lý rõ, edit toàn phần hoặc gia tăng được áp dụng theo đúng thứ tự, version và position encoding được tôn trọng, cùng với snapshot bất biến và kiểm tra kết quả bất đồng bộ, server có thể cung cấp diagnostics và tính năng ngôn ngữ nhất quán ngay cả khi tài liệu thay đổi liên tục, chưa lưu hoặc có nhiều module phụ thuộc.

