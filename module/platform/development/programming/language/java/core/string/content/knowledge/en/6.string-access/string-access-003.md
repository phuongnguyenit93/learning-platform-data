# codePointAt and codePointBefore in Java String

The two methods **String.codePointAt(int index)** and **String.codePointBefore(int index)** let you read a *Unicode code point* from a Java string in two directions: starting at the specified position or immediately before the specified position. The decisive rule for using them correctly is: **the index in both methods is measured in UTF-16 code units (`char` positions), not in code point order or visible character count**.

This lesson focuses on how to retrieve code points, recognize surrogate pairs, choose valid indices, and iterate over a string without accidentally splitting a code point outside the Basic Multilingual Plane (BMP).

## 1. Why is charAt() not enough to read every Unicode character?

A Java String stores a sequence of UTF-16 code units. One code unit is a 16-bit value; **charAt(index)** returns exactly one code unit of type char.

- Code points in the BMP outside the surrogate range (for example U+0041 for "A") are normally represented by **one** UTF-16 code unit.
- A supplementary code point outside the BMP (from U+10000 to U+10FFFF, for example U+1F600 for the emoji 😀) requires **two** code units: a *high surrogate* followed by a *low surrogate*.
- If you call charAt() on one half of a surrogate pair, the returned value is only a char representing that half; it does not equal the original code point.

Example with the string **"A😀B"**:

| UTF-16 index | Code unit at position | Role |
|---:|---|---|
| 0 | U+0041 | Letter A |
| 1 | U+D83D | High surrogate of 😀 |
| 2 | U+DE00 | Low surrogate of 😀 |
| 3 | U+0042 | Letter B |

Therefore, **length() equals 4**, even though the string has **3 Unicode code points**: A, 😀, and B. UTF-16 length is not the number of code points and is not automatically the number of visible characters (*grapheme clusters*).

The methods codePointAt()/codePointBefore() recognize **an adjacent valid surrogate pair** and combine them into the corresponding code point, instead of returning only a single char like charAt().

## 2. String.codePointAt(int index): reading from the start position

Syntax:

~~~java
int codePoint = text.codePointAt(index);
~~~

Rules:

1. index is the position of the first UTF-16 code unit to read.
2. If the char at index is a **high surrogate** and immediately after it is a **low surrogate**, the method combines both and returns the supplementary code point as an int.
3. In all other cases, the method returns the char code unit value at index as an int. This includes an unpaired surrogate or starting at a **low surrogate**, i.e., in the middle of a pair.
4. The method **does not modify** the String.

With "A😀B":

| Call | Hex result | Explanation |
|---|---|---|
| codePointAt(0) | U+0041 | Reads A |
| codePointAt(1) | U+1F600 | Combines high surrogate at index 1 and low surrogate at index 2 |
| codePointAt(2) | U+DE00 | Starts at low surrogate: returns only this code unit |
| codePointAt(3) | U+0042 | Reads B |

**Important mistake:** codePointAt(2) does not mean “get the 3rd code point”. It means read the code point **starting at UTF-16 index 2**. If the index is in the middle of a surrogate pair, the method does not look backward for the high surrogate.

Valid index bounds for a string of length n:

- **0 <= index < n** for codePointAt(index).
- For an empty string, there is no valid index.
- A negative index or index >= n throws **StringIndexOutOfBoundsException**.

### When to use it?

Use codePointAt() when you already have a **UTF-16 offset** and want the code point starting there. For example, scanning a string from left to right, classifying code points with Character.isLetter(int), Character.isDigit(int), or processing a Unicode character that does not fit in 16 bits.

## 3. String.codePointBefore(int index): reading immediately before a boundary

Syntax:

~~~java
int codePoint = text.codePointBefore(index);
~~~

Unlike codePointAt(), the index parameter **does not** point to the element to read, but rather to **the boundary immediately after the last code unit to inspect**.

Rules:

1. The method looks at the char at **index - 1**.
2. If that is a **low surrogate** and the char at **index - 2** is a **high surrogate**, the method combines the pair and returns the supplementary code point.
3. If there is no valid pair looking backward, the method returns the char value at index - 1 as an int.
4. The source String is not modified.

With "A😀B":

| Call | Hex result | Explanation |
|---|---|---|
| codePointBefore(1) | U+0041 | The character immediately before boundary 1 is A |
| codePointBefore(2) | U+D83D | Immediately before boundary 2 is the high surrogate; there is no low surrogate to its left to pair with |
| codePointBefore(3) | U+1F600 | Looking backward from index 3: low surrogate at 2 pairs with high at 1 |
| codePointBefore(4) | U+0042 | The character immediately before boundary 4 is B |

**Difference to remember:** to get the full emoji 😀, codePointAt(1) starts at the high surrogate; codePointBefore(3) starts from the boundary **after** the low surrogate.

Valid index bounds for a string of length n:

- **1 <= index <= n** for codePointBefore(index).
- index equal to n is completely valid and reads the last code point.
- index equal to 0, negative, or greater than n throws **StringIndexOutOfBoundsException**.

### When to use it?

Use codePointBefore() when you have an offset located **after** the position to read: for example iterating backward from the end of a string, reading the code point preceding a cursor, or stepping backward along UTF-16 boundaries.

## 4. Direct comparison of the two methods

| Question | codePointAt(index) | codePointBefore(index) |
|---|---|---|
| Which direction does it read? | From position index to the right | From before index to the left |
| Unit of index? | UTF-16 code unit | UTF-16 code unit |
| Which char is inspected first? | index | index - 1 |
| When is a surrogate pair combined? | index is high and index+1 is low | index-1 is low and index-2 is high |
| Valid indices? | [0, length()-1] | [1, length()] |
| Get the first code point | codePointAt(0) | codePointBefore(UTF-16 length of the first code point) |
| Get the last code point | codePointAt(start offset of the last code point) | codePointBefore(length()) |
| Return type | int | int |
| Is the string modified? | No | No |

**Memory tip:** *At* reads the code point **starting at** index; *Before* reads the code point **ending immediately before** index.

If index points to a natural boundary between two code points, both methods are helpful and consistent. If index splits a surrogate pair, the result may be only one half of the surrogate. Java does not automatically guarantee that an application-supplied index lies on a code point boundary.

## 5. Standalone Java 17+ program

The following example prints values in U+... format to avoid depending on emoji font rendering in the console. It demonstrates both accessing at proper boundaries and accessing between two surrogate halves.

Create a file **CodePointAccessDemo.java** with the content:

~~~java
public class CodePointAccessDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        System.out.println("length=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("at(%d)=U+%X%n", i, text.codePointAt(i));
        }

        for (int i = 1; i <= text.length(); i++) {
            System.out.printf("before(%d)=U+%X%n", i, text.codePointBefore(i));
        }

        System.out.println("highSurrogate="
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("lowSurrogate="
                + Character.isLowSurrogate(text.charAt(2)));
    }
}
~~~

Save the source code in UTF-8, then compile/run:

~~~bash
javac -encoding UTF-8 CodePointAccessDemo.java
java CodePointAccessDemo
~~~

Exact output:

~~~text
length=4
codePoints=3
at(0)=U+41
at(1)=U+1F600
at(2)=U+DE00
at(3)=U+42
before(1)=U+41
before(2)=U+D83D
before(3)=U+1F600
before(4)=U+42
highSurrogate=true
lowSurrogate=true
~~~

Explanation:

- length() counts **4 UTF-16 code units**, while codePointCount(0, length()) counts **3 code points**.
- codePointAt(1) and codePointBefore(3) both recognize the emoji U+1F600.
- codePointAt(2) returns only the low surrogate U+DE00; codePointBefore(2) returns only the high surrogate U+D83D.
- %X in printf displays an int in hexadecimal with uppercase A–F, so the lines above do not depend on the system locale.

## 6. Iterating through a string without splitting surrogate pairs

### 6.1. Iterating from left to right

Common mistake:

~~~java
for (int i = 0; i < text.length(); i++) {
    int codePoint = text.codePointAt(i);
    // Process codePoint...
}
~~~

This is an **illustrative code snippet**, assuming variable text is already declared. For a string with supplementary code points, the loop increments i by exactly **1 code unit**; after reading the full emoji at the high surrogate, the next iteration reads the low surrogate separately. This can process an extra value by mistake.

The right approach is to increment i by the **number of code units of the code point just read**:

~~~java
for (int i = 0; i < text.length(); ) {
    int codePoint = text.codePointAt(i);
    System.out.printf("%d: U+%X%n", i, codePoint);
    i += Character.charCount(codePoint);
}
~~~

Character.charCount(codePoint) returns 2 for a valid supplementary code point and 1 for remaining values. With text = "A😀B", output:

~~~text
0: U+41
1: U+1F600
3: U+42
~~~

The cursor jumps over both code units of the emoji: from position 1 to position 3. It does not land on the low surrogate at position 2.

### 6.2. Iterating from right to left

Initialize the cursor at **length()** and use codePointBefore(index); after each read, subtract the exact number of code units of the code point:

~~~java
for (int i = text.length(); i > 0; ) {
    int codePoint = text.codePointBefore(i);
    i -= Character.charCount(codePoint);
    System.out.printf("%d: U+%X%n", i, codePoint);
}
~~~

With text = "A😀B", output:

~~~text
3: U+42
1: U+1F600
0: U+41
~~~

**Note:** both loops above operate on code point boundaries when starting from the beginning/end of the string. If you manually place the initial cursor in the middle of a surrogate pair, both codePointAt() and codePointBefore() can return an unpaired surrogate. Determine valid offsets from the start or end of the string, or use offsetByCodePoints() when converting from a code point count.

### 6.3. When you need the position of the nth code point

codePointAt()/codePointBefore() do not directly take a **code point index**. To find the UTF-16 offset after advancing past n code points, use String.offsetByCodePoints(startUtf16Offset, n), and then call codePointAt():

~~~java
String text = "A😀B";
int utf16Offset = text.offsetByCodePoints(0, 2);
int codePoint = text.codePointAt(utf16Offset);

System.out.println(utf16Offset); // 3
System.out.printf("U+%X%n", codePoint); // U+42
~~~

In this example, after the two code points A and 😀, the UTF-16 offset is 3 rather than 2. offsetByCodePoints() also requires a valid index and offset; it can throw IndexOutOfBoundsException if it exceeds the available range.

If you only need to iterate forward over all code points and do not need UTF-16 offsets, you can use **text.codePoints()**, an IntStream of code point int values:

~~~java
String text = "A😀B";
text.codePoints().forEach(cp -> System.out.printf("U+%X%n", cp));
~~~

Output:

~~~text
U+41
U+1F600
U+42
~~~

codePoints() is useful when processing each code point as a stream of numbers, whereas codePointAt()/codePointBefore() are suitable when you need explicit control over UTF-16 positions.

## 7. Handling empty strings, boundaries, and errors

Check the **different bounds** of the two APIs before calling them.

| String | Call | Result |
|---|---|---|
| "AB" | codePointAt(0) | 65, i.e., U+0041 |
| "AB" | codePointAt(2) | StringIndexOutOfBoundsException error |
| "AB" | codePointBefore(2) | 66, i.e., U+0042 |
| "AB" | codePointBefore(0) | StringIndexOutOfBoundsException error |
| "" | codePointAt(0) | StringIndexOutOfBoundsException error |
| "" | codePointBefore(0) | StringIndexOutOfBoundsException error |

Both methods have return type int because a supplementary code point needs more than 16 bits; do not cast the result to char if you want to preserve code points U+10000 and above. If you need to convert a valid code point into a sequence of UTF-16 chars, you can use **Character.toChars(codePoint)**.

Standalone program example testing boundaries:

~~~java
public class CodePointBoundaryDemo {
    public static void main(String[] args) {
        String text = "AB";
        System.out.println(text.codePointAt(0));
        System.out.println(text.codePointBefore(text.length()));

        try {
            text.codePointBefore(0);
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println("Invalid before index");
        }

        try {
            text.codePointAt(text.length());
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println("Invalid at index");
        }
    }
}
~~~

~~~bash
javac CodePointBoundaryDemo.java
java CodePointBoundaryDemo
~~~

Output:

~~~text
65
66
Invalid before index
Invalid at index
~~~

In real code, if the input is an offset supplied by a user or another API, validate the index domain or handle exceptions appropriately. Avoid blindly subtracting/adding 1 before knowing whether that offset represents a **UTF-16 code unit**, a **code point index**, or a **display position**.

## 8. Tricky Unicode cases: unpaired surrogates and grapheme clusters

### 8.1. Surrogates that do not form a valid pair

A Java String can contain **unpaired surrogates** (a UTF-16 sequence not well-formed into complete pairs). When codePointAt()/codePointBefore() does not find an appropriate high–low pair, it returns the surrogate char value as an int. The method does not automatically replace malformed data with U+FFFD and does not throw an error solely for encountering an unpaired surrogate.

Therefore, “an int value returned from codePointAt” does not always mean a valid *Unicode scalar value*: a value in the surrogate range U+D800–U+DFFF indicates an unpaired surrogate code unit. When processing external data, inspect string quality and input encoding/decoding rules.

### 8.2. A code point is not a user-perceived character

For example, a character that displays like "é" can be represented by the letter e (U+0065) combined with an acute accent (U+0301), i.e., **two code points**. Some emoji combine multiple code points, variation selectors, or zero-width joiners. codePointAt()/codePointBefore() read **code points**, and do not automatically group an entire *grapheme cluster* into a single display character.

Therefore:

- To iterate over individual Unicode values: use codePointAt()/codePointBefore() or codePoints().
- To count/locate code points: use codePointCount() and offsetByCodePoints().
- To split character clusters as seen by the user in a UI: you need a grapheme cluster segmentation algorithm suited to your requirements and Unicode version; codePointAt() alone is not enough.

## 9. API selection checklist and common mistakes

1. **Read one UTF-16 code unit:** charAt(index).
2. **Read one code point starting at a UTF-16 offset:** codePointAt(index).
3. **Read one code point before a UTF-16 offset:** codePointBefore(index).
4. **Step across code points when iterating forward/backward:** add or subtract Character.charCount(codePoint), do not always increment/decrement by 1.
5. **Convert a code point count to a UTF-16 offset:** offsetByCodePoints().
6. **Count code points in a range:** codePointCount(startUtf16, endUtf16).
7. **Iterate over all code points as numbers:** codePoints().

Common mistakes to avoid:

- Treating **index** in codePointAt()/codePointBefore() as the code point ordinal.
- Calling codePointBefore(0) thinking it is “the first code point”; index 0 is a boundary with **no code units before it**.
- Calling codePointAt(length()) to get the last code point; that index is already **past** the end of the string.
- Looping with i++ and codePointAt(i) and double-counting a low surrogate after already pairing it.
- Assuming codePointAt() can assemble a pair when index is at the low surrogate.
- Casting a supplementary code point from int to char and losing information.
- Equating a code point with a single displayed “letter”, especially in Vietnamese with combining accents or composite emoji.

**Conclusion:** both **codePointAt(index)** and **codePointBefore(index)** work with UTF-16 offsets. codePointAt() reads from a position to the right; codePointBefore() reads immediately before that position to the left. Use proper boundary indices and advance the cursor by Character.charCount() to handle supplementary code points completely without accidentally splitting surrogate pairs.
