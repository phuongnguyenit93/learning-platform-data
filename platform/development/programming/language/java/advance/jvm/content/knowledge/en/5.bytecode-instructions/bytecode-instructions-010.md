# Reading Expression, Loop, and Assignment Bytecode to Predict Execution Order

## 1. Objectives and the Right Perspective on Bytecode

To understand which action a Java program performs first and which action it performs next, you need to combine **the Java language's expression evaluation rules** with **the JVM's control flow and operand stack**. Bytecode instructions do not correspond one-to-one with each line of source code: a single expression can become multiple instructions for loading operands, invoking methods, computing, duplicating, storing variables, and branching; a loop is usually a collection of labels/offsets and jump instructions.

After this lesson, you will:

- Know how to read **javap -c**: offsets, opcodes, operands, constant-pool references, and jump instruction targets.
- Track **local variable slots** and the **operand stack** when executing **iload**, **istore**, **iadd**, **imul**, **iinc**, and **ireturn**.
- Predict the order of operands, method calls, assignments, **++i**, **i++**, **+=**, and array element accesses.
- Analyze **if/else**, **for**, **while**, **do-while**, **continue**, **break**, **&&**, **||**, and the ternary operator using a control-flow graph.
- Distinguish an execution order **guaranteed by Java** from a bytecode generation strategy **chosen by javac**.
- Avoid misreading the order of lines in a disassembly as the order in which every line is executed; when there are branches/loops, you must trace the actual **program counter (PC)**.

The examples use Java 17+; some opcodes are presented as **representative bytecode illustrations**. You need to run **javap** on the exact class file you compile to know the exact offsets and instructions.

## 2. Execution Frame: Frame, Locals, Operand Stack, and PC

Each time a Java method is invoked, the JVM creates a frame containing, among other components, a **local variables table (local variables)** and an **operand stack**. The PC points to the next instruction to be executed in the bytecode stream of the currently running method.

~~~text
            Java bytecode of the method
        offset 0 -> instruction A
        offset 1 -> instruction B
        offset 4 -> instruction C       <---- PC may jump here
        offset 7 -> instruction D
        offset 8 -> instruction E
                         |
                         v
Currently executing frame:
  Local variables:
    slot 0: parameter / this / variable
    slot 1: another variable
    ...
  Operand stack:
    top -> most recently pushed value
           values waiting to be processed
  ...
~~~

Basic manipulation rules:

1. A **load** instruction usually reads a local slot and **pushes** the value onto the operand stack.
2. A computation instruction usually **pops** operands from the stack and **pushes** the result back.
3. A **store** instruction usually **pops** a value from the stack and writes it to a local slot.
4. A conditional branch instruction pops the value(s) to check and decides whether the PC goes to the jump target or the next instruction.
5. A method invocation instruction prepares the receiver and arguments according to JVM conventions; the invoked method creates its own frame, and may later return a result to the caller.
6. **return/ireturn/...** terminates the current frame and returns to the caller, except in cases of abrupt completion via an exception.

Stack simulation example when executing **(a + b) * 2**, with **a=3, b=4**:

| Illustrative instruction | Locals | Operand stack after instruction (bottom → top) |
| --- | --- | --- |
| Before running | a=3, b=4 | **[]** |
| **iload_0** | unchanged | **[3]** |
| **iload_1** | unchanged | **[3, 4]** |
| **iadd** | unchanged | **[7]** |
| **iconst_2** | unchanged | **[7, 2]** |
| **imul** | unchanged | **[14]** |
| **ireturn** | method completes | Returns **14** to caller |

The table only illustrates a **static** method with two int parameters in slots 0 and 1. In an instance method, slot 0 is usually **this**. Actual instructions may differ due to constant folding, locals layout, or different compilers.

### 2.1. Common Opcodes

| Group | Opcode | Role |
| --- | --- | --- |
| Load constant | **iconst_0**, **iconst_1**, **bipush**, **sipush**, **ldc** | Pushes a constant onto the stack |
| Load local | **iload**, **iload_0**... | Pushes an int from a local slot |
| Store local | **istore**, **istore_0**... | Pops an int from the stack and writes it to a slot |
| Arithmetic | **iadd**, **isub**, **imul**, **idiv**, **irem** | int operations, operands popped from the stack |
| Increment local | **iinc index, delta** | Adds constant delta directly to a local int; does not pop/push the operand stack |
| Single int condition | **ifeq**, **ifne**, **iflt**, **ifle**, **ifgt**, **ifge** | Compares against 0, branches |
| Compare two ints | **if_icmpeq**, **if_icmpne**, **if_icmpge**... | Pops two ints, checks the relation |
| Unconditional jump | **goto**, **goto_w** | Changes PC to an offset |
| Return | **ireturn**, **areturn**, **return** | Terminates the method |
| Duplicate/swap | **dup**, **dup_x1**, **dup2**, **swap** | Organizes values on the stack, useful in assignments/++ |
| Array | **iaload**, **iastore**, **arraylength** | Reads, writes, and gets the length of an array |
| Field | **getfield**, **putfield**, **getstatic**, **putstatic** | Reads/writes instance/static fields |
| Method call | **invokestatic**, **invokevirtual**, **invokeinterface**, **invokespecial**, **invokedynamic** | Invokes or dynamically links operations |

The letter **i** indicates the **int** computational type in the JVM; source **byte**, **short**, **char**, and **boolean** are sometimes also processed through int opcodes. **long/double** use two units in the frame model and have their own opcodes.

## 3. Reading javap -c Output Without Misreading Offsets

Common syntax:

~~~bash
javac --release 17 FileName.java
javap -c -p FileName
~~~

Sample notation:

~~~text
  0: iload_0
  1: iload_1
  2: iadd
  3: ireturn
~~~

- **0, 1, 2, 3** are **bytecode offsets**, not source line numbers.
- **iload_0** may be a 1-byte instruction; instructions with operands may be longer.
- An instruction like **6: if_icmpge 19** means if the condition is true, the PC goes to offset **19** in the same method; if false, it proceeds to the next instruction. The number **19** printed in javap is the **target offset**, not a boolean value.
- **#n** after opcodes like **invokevirtual #n**, **getfield #n** is a constant pool reference index, not a machine code address or runtime value.
- Comments after **//** usually explain the constant pool reference, method descriptor, or type. They help locate the exact method/field being called.

When there is a loop, the order of lines appearing in javap is the **instruction storage order**, not a sequence of actions executed only once. You must follow the PC and every branch target, including backward **goto** jumps.

### 3.1. Connecting with Source Code

Use additionally:

~~~bash
javap -c -p -l FileName
javap -v -p FileName
~~~

- **-l** displays line/local-variable tables **if present**; not every class file includes full debug metadata.
- **-v** displays the constant pool, Code attributes, StackMapTable, and other details for inspection.
- **-p** allows viewing private members as well.

You should not assume every Java statement produces a separate contiguous range of bytecode or that source line numbers increase monotonically with PC. The compiler may fold constants, generate synthetic methods, optimize away unnecessary branches, change loop structures, and reorder instruction layout as long as Java semantics are preserved.

## 4. Left-to-Right Expression Evaluation: Evaluation Order Differs from Precedence

The **Java Language Specification (JLS §15.7)** guarantees that operands of many expressions are evaluated **from left to right** according to the rules of each expression form. This must be distinguished from **precedence** (operator priority) and **associativity** (how expressions are grouped).

Example:

~~~java
// Illustration inside a Java method.
int result = left() + right() * 4;
~~~

**right() * 4** is grouped with multiplication because multiplication has higher precedence than addition, **but left() is still called before right()** because the left operand of addition is evaluated before the right operand.

A valid order of actions:

~~~text
1. Call left() and obtain its result.
2. Call right() and obtain its result.
3. Multiply the return value of right() by 4.
4. Add the result of left() to that product.
5. Store the sum into result.
~~~

The compiler may use the operand stack to hold the result of **left()** while continuing to evaluate the right-hand side.

**Do not conclude:** “Multiplication has higher precedence, so side effects in right() must occur before side effects in left().” Precedence determines **the structure of operations**, whereas evaluation order determines **when each operand is evaluated**.

### 4.1. Method Arguments Are Also Evaluated in Order

~~~java
// Illustrative example:
combine(first(), second(), third());
~~~

In Java, the method receiver expression (if any) is processed according to invocation rules, and then the argument expressions are evaluated from left to right. If **first()** throws an exception, **second()** and **third()** are not evaluated; the compiler cannot arbitrarily reorder them for optimization.

When reading bytecode, track the **invoke...** instructions and where their results are pushed onto the stack. The actual call to **combine** occurs once the required arguments have all been evaluated.

### 4.2. Exceptions and Side Effects Are Proof of Order

Illustrative example:

~~~java
// Illustration, not a standalone program:
int value = 10 / divisor() + logAndReturn(3);
~~~

If **divisor()** returns **0**, the integer division instruction throws **ArithmeticException** before Java evaluates the **logAndReturn(3)** operand after the addition. Therefore, the side effect of **logAndReturn** does not occur.

An optimizer/JIT may change the internal implementation, but the observable result must preserve Java rules such as required side effects/exceptions. Do not infer from a disassembly lacking side effects that Java has no evaluation order.

## 5. Runnable Example 1: Observing Order via Console

Create the file **BytecodeOrderDemo.java**:

~~~java
public class BytecodeOrderDemo {
    static int next(String name, int value) {
        System.out.println("eval:" + name);
        return value;
    }

    static boolean left() {
        System.out.println("check:left");
        return false;
    }

    static boolean right() {
        System.out.println("check:right");
        return true;
    }

    public static void main(String[] args) {
        int expression = next("A", 2) + next("B", 3) * 4;
        System.out.println("expr=" + expression);

        int x = 4;
        int assigned = (x = 7) + x++;
        System.out.println("assign:result=" + assigned + ",x=" + x);

        int p = 2;
        int increments = ++p + p++;
        System.out.println("inc:both=" + increments + ",p=" + p);

        boolean shortCircuit = left() && right();
        System.out.println("and=" + shortCircuit);

        boolean eagerAnd = left() & right();
        System.out.println("eagerAnd=" + eagerAnd);

        int[] array = {10, 20};
        int index = 0;
        array[index++] += next("delta", 3);
        System.out.println("array:first=" + array[0] + ",index=" + index);

        int sum = 0;
        for (int i = 0; i < 4; i++) {
            if (i == 1) {
                continue;
            }
            if (i == 3) {
                break;
            }
            sum += i;
        }
        System.out.println("loop=" + sum);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 BytecodeOrderDemo.java
java BytecodeOrderDemo
~~~

**Exact stdout:**

~~~text
eval:A
eval:B
expr=14
assign:result=14,x=8
inc:both=6,p=4
check:left
and=false
check:left
check:right
eagerAnd=false
eval:delta
array:first=13,index=1
loop=2
~~~

Why is the order like this?

1. **next("A",2)** is called before **next("B",3)** even though multiplication has higher precedence than addition. The sum is **2 + 3 * 4 = 14**.
2. **(x = 7)** assigns **x** to 7 and the assignment expression has value 7. **x++** returns the old value 7 and then increments x to 8; **assigned = 7 + 7 = 14**.
3. **++p** increments p from 2 to 3 and returns 3; **p++** returns 3 and increments p to 4; the sum expression is **6**.
4. **left() && right()** stops when left returns false, so **right() does not run**.
5. **left() & right()** when applied to booleans still evaluates **both sides**, resulting in false.
6. **array[index++] += next("delta",3)** accesses the element at the old index 0, remembers its current value 10, evaluates delta = 3, and writes 13 into **array[0]**; index becomes 1.
7. The for loop goes through i=0 (adds 0), i=1 (continues then updates i), i=2 (adds 2), i=3 (breaks). Result **sum=2**.

The example intentionally uses expressions with side effects to make evaluation order clearly visible. In real production code, separating side effects onto their own lines usually improves maintainability and prevents confusion.

## 6. Simple Assignment: Storing into a Local, Field, or Array

Consider:

~~~java
// Illustrative example:
int a = 2;
int b = 5;
a = b + 3;
~~~

A typical bytecode organization:

~~~text
... push 2; store a
... push 5; store b

load b
push 3
iadd
store a
~~~

The key point is that **b + 3** is computed before the new value is written to **a**. Assignment in Java is an **expression**: after executing, it has a value usable by an enclosing expression.

For example, **int z = (a = 7) + a;**: the assignment on the left happens before reading **a** on the right, so both operands equal 7 (assuming no external concurrent modification), resulting in 14.

### 6.1. Local Variables and the Operand Stack Are Two Different Places

Do not mistake **istore_1** for “pushing a value onto the stack”: this opcode pops the value currently on the stack and **stores it down** into local slot 1. **iload_1** does the reverse. The operand order of **isub/idiv** is especially important: stack **[a, b]** (b on top) followed by **isub** gives **a - b**, not **b - a**.

Stack example:

~~~text
iconst_3     -> [3]
iconst_2     -> [3, 2]
isub         -> [1]
~~~

### 6.2. Assignment May Need to Retain the Result Value

If the assigned value is still used, for example:

~~~java
// Illustration:
int a;
int b;
b = (a = 5);
~~~

The compiler may use **dup** or an equivalent stack arrangement to both store into **a** and keep the value 5 for assigning to **b**. If the assignment is a standalone statement, there is no need to retain the value after storing.

That is why instructions like **dup**, **dup_x1**, and **dup_x2** often appear near field/array assignments, increment expressions, and operations that both write and need to return a value. You should not reverse-infer that the presence of **dup** means the source code wrote a specific assignment form.

## 7. Prefix ++i, Postfix i++, and iinc

For a local variable of type **int**:

~~~java
int i = 3;
int oldValue = i++; // oldValue = 3, i = 4
int newValue = ++i; // newValue = 5, i = 5
~~~

The difference is **the value of the expression**, not just the timing of the update:

| Expression | Variable value after operation | Expression value |
| --- | ---: | ---: |
| **i++**, previously i=3 | 4 | 3 |
| **++i**, previously i=3 | 4 | 4 |
| **i--**, previously i=3 | 2 | 3 |
| **--i**, previously i=3 | 2 | 2 |

**iinc index, delta** is a JVM instruction that increments a local int without going through the operand stack. If the value of **i++** needs to be kept, the compiler can **iload** the old value before **iinc**; if it is **++i**, it can **iinc** first and then **iload** the new value.

**Illustrative** bytecode example, not guaranteed that every javac chooses this exact sequence:

~~~text
i++ when the old value is needed:
    iload <slot>
    iinc <slot>, 1

++i when the new value is needed:
    iinc <slot>, 1
    iload <slot>
~~~

If **i++;** is written solely as a statement, the old value is unused, so the compiler may emit only **iinc**. For fields, array components, **long** types, or expressions with complex side effects, **iinc** cannot simply be applied in all cases; the bytecode may need **getfield/putfield**, **iaload/iastore**, **dup**, and appropriate typed opcodes.

### 7.1. ++ Is Not Identical to += in Every Case

In Java source, **i++** has the rule of returning the old value, **++i** returns the new value; **i += 1** is a compound assignment that returns the updated value. For a local **int** with no other side effects, a compiler may use the same **iinc** as the update step, but when the expression needs a value it must preserve the proper load-before/after behavior.

Example **int r = i++ + ++i;** with **i = 1**:

~~~text
left side i++  -> returns 1, i becomes 2
right side ++i -> i becomes 3, returns 3
r = 1 + 3 = 4, final i = 3
~~~

This is valid Java with a well-defined evaluation order, even though writing code that depends on multiple side effects is very error-prone during code review.

## 8. Compound Assignment += and Left-Hand Side Evaluation Order

The operation **x += expr** has the same effect as **x = (T) (x + expr)** for the type T of x, **except** that the expression identifying the variable on the left-hand side is evaluated **only once** and the old value is read/remembered according to compound assignment semantics.

Example:

~~~java
// Illustration inside a method:
int x = 10;
x += 3; // x = 13
~~~

With a local **int** and a suitable constant, javac may compile it into an **iinc** form instead of mandating **iload; iconst; iadd; istore**. Therefore, you should compare **behavior** and stack/local effects rather than forcing every += into four fixed instructions.

### 8.1. Case of ++ Inside an Array Index

~~~java
// Illustration:
int[] values = {10, 20};
int k = 0;
values[k++] += 3;
~~~

Behavior:

1. Determine the array reference **values** and the index expression **k++** (old index value = 0, then k=1).
2. Perform appropriate element access checks and read **values[0] = 10**.
3. Evaluate RHS **3**; add to get 13.
4. Write back **values[0] = 13**.

The result is **values[0] = 13** and **k = 1**. **The index expression is evaluated only once**, not twice as in a careless rewrite:

~~~java
// NOT equivalent, because k++ is executed twice:
values[k++] = values[k++] + 3;
~~~

The bytecode pattern for compound array assignment typically has to keep the reference, index, and old value on the stack via instructions such as **dup2**, **iaload**, **iadd**, **iastore**. The exact instruction sequence varies by array type and compiler.

### 8.2. Why += on byte Can Use i2b?

~~~java
byte b = 127;
b += 1;        // Valid; b becomes -128
// b = b + 1;  // Compile-time error: b + 1 has type int
~~~

The Java language allows compound assignment with an implicit narrowing conversion to the target type. The JVM can compute via int and then use **i2b** to bring the result back to byte semantics. You should not assume every byte variable is added directly by a “byte add” instruction; the **iadd** opcode operates on the int computational type.

## 9. Field and Array Assignment: Identifying Side-Effect Order

### 9.1. Object Field Assignment

Example:

~~~java
// Illustration in a class with an int value field:
holder().value = compute();
~~~

Java must evaluate the expression determining the receiver (here **holder()**) before the RHS, subject to the checking and assignment constraints of field access. The bytecode may contain calls to **holder**, **compute**, and **putfield**. If the receiver is null, the effect and timing of throwing **NullPointerException** must be analyzed according to the Java rules for that assignment form, not solely by looking at the final opcode name.

If there is **holder().value += compute()**, the compiler must preserve the old field value and evaluate the receiver identity once; **getfield** and **putfield** may appear.

### 9.2. Array Assignment and Index Checking

The Java specification distinguishes the order of checks in **simple assignment** versus **compound assignment** to an array component.

- With **array[index] = rhs()** (simple assignment), Java evaluates the array reference and index, and then evaluates the RHS before performing the array store step and the runtime checks attached to the store step according to the corresponding rules.
- With **array[index] += rhs()** (compound assignment), after evaluating the array reference/index, Java performs null/bounds checks and reads the old value of the element **before** evaluating the RHS.

This is an observable difference if the RHS has side effects or throws an exception. You must not assume both always invoke the RHS before/after **ArrayIndexOutOfBoundsException** in the same order.

To analyze a specific program:

1. Identify whether it is a **simple** or **compound** assignment.
2. Track the array reference and index expressions in order.
3. Mark when null/bounds checks and element reads occur, if any.
4. Track the RHS, the operation, and the corresponding **xastore** array write instruction.

**Useful practice:** compile a small example with logging in the index/RHS, then use **javap -c** to locate **iaload/iastore** and the calls. This is a case where you must stick to JLS semantics and avoid guessing purely from source appearance.

## 10. if/else Branching: Following Each Edge of the Control-Flow Graph

An **if** statement is usually turned into **comparison + conditional jump + unconditional jump** if there is an else. Example:

~~~java
static int absLike(int value) {
    if (value >= 0) {
        return value;
    } else {
        return -value;
    }
}
~~~

An illustrative bytecode layout:

~~~text
  iload value
  iflt NEGATIVE
  iload value
  ireturn
NEGATIVE:
  iload value
  ineg
  ireturn
~~~

In the JVM, **iflt** pops an int from the stack and checks **value < 0**. If true, it jumps to the NEGATIVE branch; if false, execution continues to the part that returns value. This expresses the same semantics as **if (value >= 0)** where the branch is written on the negated condition.

**Do not misread:** the source has **>=**, but the opcode may be **iflt** to jump past the true branch. When reading bytecode, you must look at **opcode + target + fall-through path** as a whole.

### 10.1. ifeq/ifne for boolean

With:

~~~java
// Illustration:
if (ready) {
    act();
}
~~~

Computationally in the JVM, **ready** may be represented as an int, and the compiler uses **ifeq** to jump past **act()** when the value is false (0). This does not mean **ready** in Java becomes a numeric type that can be added or subtracted; it remains boolean at the language level.

### 10.2. if_icmpge Differs from ifge

- **ifge** pops **one int** and compares it against 0.
- **if_icmpge** pops **two ints** and checks whether the first value is greater than or equal to the second value.
- **if_acmpeq/if_acmpne** checks reference identity/equality of two references, without executing **equals(...)**.
- **ifnull/ifnonnull** checks whether a reference is null.

When analyzing the condition **i < limit**, you may encounter **if_icmpge** to jump out of the loop when the condition is **no longer** true.

## 11. Reading a for Loop: Initialization, Check, Body, Update

Source code:

~~~java
static int sumBefore(int limit) {
    int sum = 0;
    for (int i = 0; i < limit; i++) {
        sum += i;
    }
    return sum;
}
~~~

Conceptual control flow:

~~~text
START
  |
  v
sum = 0, i = 0
  |
  v
CHECK: i < limit? --- false ---> EXIT: return sum
  |
 true
  v
BODY: sum += i
  |
  v
UPDATE: i++
  |
  +------------------------> CHECK
~~~

Illustrative bytecode with locals **slot 0=limit, slot 1=sum, slot 2=i** (actual offsets may depend on the compiler):

~~~text
 0: iconst_0
 1: istore_1              // sum = 0
 2: iconst_0
 3: istore_2              // i = 0
 4: iload_2               // CHECK: push i
 5: iload_0               // push limit
 6: if_icmpge 19          // i >= limit -> EXIT
 9: iload_1               // push sum
10: iload_2               // push i
11: iadd                  // sum + i
12: istore_1              // sum = ...
13: iinc 2, 1             // i++
16: goto 4                // loop back to CHECK
19: iload_1
20: ireturn
~~~

Tracing **sumBefore(4)**:

| Check iteration | i | i < 4? | sum before body | Activity |
| --- | ---: | --- | ---: | --- |
| 1 | 0 | true | 0 | Add 0; i becomes 1 |
| 2 | 1 | true | 0 | Add 1; i becomes 2 |
| 3 | 2 | true | 1 | Add 2; i becomes 3 |
| 4 | 3 | true | 3 | Add 3; i becomes 4 |
| 5 | 4 | false | 6 | Jump to ireturn |

The return value is **6**. The **goto 4** arrow is the reason the CHECK/BODY/UPDATE group runs repeatedly; if you only read from lower offsets to higher offsets once, you will predict incorrectly.

### 11.1. for and while Are Often the Same Idea in Bytecode

With equivalent semantics:

~~~java
int i = 0;
while (i < limit) {
    sum += i;
    i++;
}
~~~

The compiler may emit control flow very similar to **for**, because both check the condition before running the body. **for** simply groups initialization, condition, and update into one syntax.

However, the **scope** of variable **i**, the placement of the update, and the path of **continue** must be preserved according to the language rules. Visually rewriting a for loop as a while loop is not equivalent in all cases.

## 12. while, do-while, continue, and break

### 12.1. while Checks Before, do-while Checks After

~~~java
int a = 0;
while (a < 0) {
    a++;
}

int b = 0;
do {
    b++;
} while (b < 0);
~~~

After both loops: **a = 0**, **b = 1**. **while** does not execute its body at all because the condition is false on the first check; **do-while** executes its body at least once before evaluating the condition.

Diagram:

~~~text
while:
  CHECK? ---- false ----> EXIT
    |
   true
    v
   BODY ----------------> CHECK

do-while:
  BODY
    |
    v
  CHECK? ---- false ----> EXIT
    |
   true
    +-------------------> BODY
~~~

A compiler may optimize branches if it knows a condition is constant, so predict based on semantics first, then cross-check with the actual bytecode.

### 12.2. continue in for Jumps to UPDATE, Then CHECK

With:

~~~java
for (int i = 0; i < 4; i++) {
    if (i == 1) continue;
    System.out.println(i);
}
~~~

The output is **0, 2, 3** on separate lines. When i=1, **continue** skips the rest of the loop body, but still executes the **i++** of the for loop before the next CHECK. In bytecode, the **continue** edge may jump to the **UPDATE** block.

In a **while** loop, continue usually goes to the **CHECK** of the enclosing loop; if you manually convert a for loop into a while loop by placing the update at the end of the body, **continue** may skip the update and cause an infinite loop.

### 12.3. break Exits the Selected Loop

**break** does not jump back to CHECK; it goes to **the point after the loop** (or the specified target with a labeled break). With two nested loops, an unlabeled **break** exits the innermost loop; **break outer;** can exit the loop labeled **outer**.

**Labeled continue** jumps to the next iteration of the correspondingly labeled loop (subject to JLS syntactic requirements). When reading bytecode, you do not necessarily see “Java label names”; you only see the target offsets computed by the compiler.

### 12.4. finally Can Make Paths More Complex

If **break**, **continue**, or **return** is inside a **try/finally** region, Java must still execute the appropriate **finally** steps when leaving the region, except for special cases per the specification. The compiler may generate additional control flow and exception handlers. When try/finally is present, you should not interpret a single **goto** as the entire behavior of break/continue while ignoring cleanup blocks.

## 13. &&, ||, and &: Looking at Branches to See Short-Circuiting

Java logical operators:

| Operator | When is RHS evaluated? | Result |
| --- | --- | --- |
| **a && b** | Only when a is true | Short-circuit logical AND |
| **a || b** | Only when a is false | Short-circuit logical OR |
| **a & b** with boolean | Always evaluates both sides | Non-short-circuit logical AND |
| **a \| b** with boolean | Always evaluates both sides | Non-short-circuit logical OR |
| **a ^ b** with boolean | Always evaluates both sides | Logical XOR |

Example:

~~~java
// Illustration:
if (isReady() && loadData()) {
    process();
}
~~~

An equivalent control flow:

~~~text
call isReady()
  if false -> END
call loadData()
  if false -> END
call process()
END:
~~~

If **isReady()** returns false, the call to **loadData()** must be skipped. The compiler usually implements this with instructions like **ifeq/ifne**; it cannot arbitrarily replace **&&** with **iand** after evaluating both sides because that could cause the RHS to run contrary to source semantics.

In a non-short-circuit expression like **isReady() & loadData()**, both sides are evaluated (left then right). The compiler may use **iand** on boolean values computed via int, or other equivalent instructions, as long as the result and side effects are preserved.

**Avoid a dangerous bug:** in the condition **obj != null && obj.isActive()**, the **&&** operator guards the method call on null. Changing it to **&** can cause a **NullPointerException**.

## 14. Ternary Operator and switch

### 14.1. condition ? trueValue : falseValue

~~~java
int result = score >= 60 ? passValue() : failValue();
~~~

Java evaluates **score >= 60**, then evaluates **only one of the two branches**. Bytecode may use a conditional instruction to jump to the corresponding block, then **goto** to merge at a common point, for example:

~~~text
evaluate condition
if false -> ELSE
call passValue
goto JOIN
ELSE:
call failValue
JOIN:
store result
~~~

Both branches are never called together just to “pick the result afterward”; side effects/exceptions must follow only the chosen branch.

### 14.2. switch Has Multiple Code Generation Strategies

For **switch** on int values or corresponding forms, bytecode may contain **tableswitch** or **lookupswitch**:

- **tableswitch** is useful for a nearly contiguous range of values, using a jump offset table.
- **lookupswitch** uses pairs of match-value and target offset.
- For string switch, enum switch, or pattern/switch expressions, the compiler may generate additional processing steps.

You must read the **tableswitch/lookupswitch** instruction itself and all target blocks, rather than guessing case execution order from the order cases appear in the disassembly. **break** in a switch and **break** in a loop have different targets depending on the control structure.

## 15. Runnable Example 2: Compact Bytecode for Instruction-by-Instruction Reading

Create the file **BytecodeLoopLab.java**:

~~~java
public class BytecodeLoopLab {
    static int multiplyAdd(int a, int b) {
        return (a + b) * 2;
    }

    static int sumBefore(int limit) {
        int sum = 0;
        for (int i = 0; i < limit; i++) {
            sum += i;
        }
        return sum;
    }

    static int sign(int value) {
        return value > 0 ? 1 : -1;
    }

    public static void main(String[] args) {
        System.out.println("multiplyAdd=" + multiplyAdd(2, 3));
        System.out.println("sumBefore=" + sumBefore(4));
        System.out.println("signZero=" + sign(0));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 BytecodeLoopLab.java
java BytecodeLoopLab
javap -c -p BytecodeLoopLab
~~~

**Exact stdout of the java command (excluding the javap output):**

~~~text
multiplyAdd=10
sumBefore=6
signZero=-1
~~~

For **multiplyAdd**, a typical **javac** compiler produces a form like:

~~~text
0: iload_0
1: iload_1
2: iadd
3: iconst_2
4: imul
5: ireturn
~~~

Trace the operand stack states:

| Offset | Instruction | Stack after instruction |
| ---: | --- | --- |
| 0 | iload_0 | [2] |
| 1 | iload_1 | [2, 3] |
| 2 | iadd | [5] |
| 3 | iconst_2 | [5, 2] |
| 4 | imul | [10] |
| 5 | ireturn | returns 10 |

This is a very suitable sample bytecode for practicing stack reading because it has no external side effects and no branches.

For **sumBefore**, compare the sequence **iload**, **if_icmpge**, **iadd**, **istore**, **iinc**, **goto** presented in section 11. For **sign**, look for a branch like **ifle** to the zero/negative case, instructions loading 1 or -1, and the join/return point. The compiler may generate:

~~~text
load value
if value <= 0 -> NEGATIVE
push 1
goto RETURN
NEGATIVE:
push -1
RETURN:
ireturn
~~~

The key takeaway is that **two different paths converge at a single return point**, rather than memorizing fixed compiler offsets.

## 16. Analyzing a Tricky Expression Case with a State Table

Consider:

~~~java
// Illustration inside a method:
int i = 1;
int value = i++ + ++i * i;
~~~

Steps according to the JLS:

| Step | Action | i after step | Held operand value |
| --- | --- | ---: | --- |
| 1 | Evaluate left side of +: **i++** | 2 | Left side of **+** holds **1** |
| 2 | Evaluate left side of *: **++i** | 3 | Left side of **\*** holds **3** |
| 3 | Evaluate right side of *: read **i** | 3 | Right side of **\*** is **3** |
| 4 | Compute multiplication **3 * 3** | 3 | Multiplication result **9** |
| 5 | Compute addition **1 + 9** | 3 | **value = 10** |

Thus the result is **value = 10**, **i = 3**. A conceptual stack view:

~~~text
i++     -> push 1, i becomes 2        stack [1]
++i     -> push 3, i becomes 3        stack [1, 3]
i       -> push 3                     stack [1, 3, 3]
imul    -> push 9 replacing 3,3       stack [1, 9]
iadd    -> push 10 replacing 1,9      stack [10]
istore  -> value = 10                 stack []
~~~

Although the expression is valid and has a well-defined result, writing multiple mutations on the same variable is unclear in production code. Analyzing bytecode helps confirm the rules, while writing readable code avoids having to analyze such cases during debugging.

## 17. Evaluation Order Cases and Compiler Optimizations

### 17.1. No One-to-One Mapping from Java Lines to JVM Instructions

Source snippet:

~~~java
int answer = 10 + 20;
~~~

The compiler may fold this into a single constant **30** instead of bytecode pushing 10, pushing 20, and then **iadd**. If the code has no side effects, preserving the result is sufficient within valid optimizations.

Conversely:

~~~java
int answer = next("A", 10) + next("B", 20);
~~~

The compiler cannot arbitrarily swap the two calls when they print different lines; side effects must reflect Java's evaluation order.

### 17.2. Javac Bytecode and JIT Machine Code Are Two Layers

**javap -c** reads **bytecode in the class file**. The JVM may interpret or JIT-compile hot methods to machine code, perform internal optimizations, inline methods, keep values in registers, or eliminate operations that do not affect observable behavior. Therefore:

- Use **javap** to understand the structure and control flow of **compiled** bytecode.
- Use execution results and the Java specification to verify **observable semantics**.
- Do not treat javap as an exact picture of the CPU instructions the JIT is running.
- Do not treat a specific bytecode shape from javac version X as a mandatory rule of the JLS.

### 17.3. Runtime Errors Change the Path

Instructions such as **idiv**, **iaload**, **getfield**, or method invocations can throw exceptions. When that happens, the PC does not simply proceed to the next offset; the JVM searches for an appropriate exception handler via the exception table, or continues unwinding the frame. Thus “reading straight from top to bottom” can be wrong even when there is no **goto** nearby.

If **finally** is present, bytecode can be more complex due to cleanup logic. To predict execution order, you must consider **all normal edges as well as exception edges**.

### 17.4. Do Not Use Bytecode Order to Predict Scheduling Between Threads

The JLS specifies expression evaluation order for **a single thread** according to program semantics. The bytecode of a method does not prove that interleaving between multiple threads is fixed. To reason about concurrent code outcomes, you must consider the **Java Memory Model**, synchronization, and happens-before relationships. Avoid inferring from thread A's PC that thread B will wait for A to reach a certain offset.

## 18. Process for Reading Bytecode to Predict Order Accurately

Instead of trying to guess an entire method, follow this iterative analysis loop:

1. **Compile the source code with the right version**, save the class file, and use **javap -c -p** to obtain instruction offsets.
2. **Identify the method descriptor** and the initial local slots reserved for **this**/parameters; understand the value types (int, long, reference...).
3. **Mark sources of side effects:** **invoke...**, **putfield/putstatic**, **xastore**, I/O, mutating methods, monitors, and operations that may throw exceptions.
4. **Build a table** containing **PC, local variables, operand stack, chosen branch, output/side effects**. Initialize the state from actual inputs.
5. **Simulate each instruction**: push/pop the stack in the right order; pay attention to non-commutative operators like subtraction and division; update locals on store or iinc.
6. **For if/loop**, evaluate the condition and move PC to the target or fall-through; never traverse both branches.
7. **For compound assignment/++**, mark the old value, new value, and how many times receiver/index expressions are evaluated; do not confuse a stack value with the current variable value.
8. **Track exceptions** when needed: a failing operation may abort evaluation of subsequent expressions or transfer to a handler.
9. **Record stdout at the exact moment println is called**, after its argument expression has been evaluated.
10. **Cross-check with the running program**, and finally explain using **JLS rules** and the observed bytecode. If there is a discrepancy, check the compiled class, JDK, inputs, threads/concurrency, and any missed side effects.

Template table to fill in yourself:

| PC | Instruction | Locals before/after | Stack before/after | Branch target | Side effect/output |
| --- | --- | --- | --- | --- | --- |
| current offset | opcode | which values changed? | what elements popped/pushed? | jump or fall-through? | print, field/array write, method call? |

This table is especially effective for code with **iinc** instructions and backward jumps: after each **goto**, you return to the exact target PC with the updated local variables.

## 19. Common Misconceptions

1. **“An instruction appearing on a lower line in javap definitely runs after an instruction on an upper line.”** False if control jumps over or repeats instructions.
2. **“Operator precedence is the order of method calls.”** False; **left() + right()*4** still evaluates left() before right().
3. **“i++ and ++i are the same because both increment i.”** Wrong when the expression's value is used: postfix returns the old value, prefix returns the new value.
4. **“iinc pushes the new value onto the stack.”** No; iinc modifies the local directly, with no operand-stack effect like iload.
5. **“istore reads a local.”** The opposite; **iload** reads a local and pushes, **istore** pops and writes a local.
6. **“&& is just & written differently.”** No; **&&** short-circuits, while **&** on booleans evaluates both sides.
7. **“In a for loop, continue skips i++ as well.”** No; continue jumps to the update step and then the condition, when it is the corresponding for loop.
8. **“if (a >= b) always generates if_icmpge.”** No; the compiler may use the negated branch **if_icmplt** to jump past the body.
9. **“A compound assignment statement is interpreted by literally copying the left-hand side twice.”** Wrong when the receiver/index has side effects; Java guarantees the left-hand side is evaluated once.
10. **“One source line = one opcode.”** No; the compiler may generate multiple instructions, fold constants, or emit code for helpers/exception tables.
11. **“The value on the operand stack is the variable itself in locals.”** No; the stack may hold an old value while the local has already been updated.
12. **“The output of a multithreaded program can be fully deduced from javap of one thread.”** No; ordering between threads requires analyzing synchronization and the memory model.

## 20. Prediction Exercises with Answers

**Exercise 1 — Prefix and Postfix**

~~~java
int x = 2;
int y = x++ + ++x;
System.out.println("x=" + x + ",y=" + y);
~~~

**Answer:** **x=4,y=6**. Left side returns 2 then x=3; right side increments x=4 then returns 4; sum is 6.

**Exercise 2 — Evaluation Order**

~~~java
int n = 1;
int result = (n = 5) * n;
System.out.println("n=" + n + ",result=" + result);
~~~

**Answer:** **n=5,result=25**. The assignment on the left completes before the right side reads n.

**Exercise 3 — Compound Assignment on Array**

~~~java
int[] a = {4, 9};
int k = 0;
a[k++] += 2;
System.out.println("a0=" + a[0] + ",k=" + k);
~~~

**Answer:** **a0=6,k=1**. The index is taken at its old value 0; the RHS is added to that element.

**Exercise 4 — Continue**

~~~java
int sum = 0;
for (int i = 0; i < 4; i++) {
    if (i == 2) continue;
    sum += i;
}
System.out.println(sum);
~~~

**Answer:** **4** (0+1+3). When i=2, continue still goes through the for-update to increment i and then re-checks the condition.

**Exercise 5 — Do-while**

~~~java
int a = 0;
do {
    a++;
} while (a < 0);
System.out.println(a);
~~~

**Answer:** **1**, because the body runs once before the condition.

**Exercise 6 — Reading a Negated Branch**

Illustrative bytecode:

~~~text
iload_0
iconst_5
if_icmplt 12
iconst_1
ireturn
12: iconst_0
ireturn
~~~

**Answer:** The method returns **1** when the parameter is **>= 5**, and returns **0** when the parameter is **< 5**. The **if_icmplt** opcode jumps to the branch returning 0, so it is the negated condition of the branch returning 1.

**Exercise 7 — Short-Circuit Evaluation**

~~~java
int n = 0;
boolean ok = (n != 0) && (10 / n > 1);
System.out.println(ok);
~~~

**Answer:** Prints **false**, does not throw **ArithmeticException**, because the right side of **&&** is not evaluated when n=0. If **&&** is changed to **&**, the division is evaluated and the error occurs.

**Exercise 8 — Operand Stack**

When the stack from bottom to top is **[8, 2]**, what value does running **idiv** produce?

**Answer:** **4**, because the first int / value below the top is the dividend 8, and the top of the stack is the divisor 2. Not 2/8.

**Exercise 9 — for Loop in javap**

You see an instruction sequence containing **if_icmpge 25**, then the body, **iinc**, **goto 4**, and **25: ireturn**. When the comparison condition **i >= limit** is true, what happens?

**Answer:** PC jumps straight to **offset 25** to return; if false, it runs the body, iinc, and goto back to offset 4.

**Exercise 10 — Analysis Limits**

You see in **javap -c** of a method two calls **A()**, **B()** in storage order, but the method is an asynchronous callback and A/B can spawn threads. Is there sufficient basis to say every log from B is always after every log from A?

**Answer:** No. The evaluation order of calls in the initial thread is governed by rules, whereas activities inside other threads can interleave. Synchronization/happens-before must be analyzed separately.

## 21. Specification References

- **Java Language Specification SE 17, §15.7 — Evaluation Order**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7
- **JLS §15.14–§15.15 — Postfix, Prefix Expressions**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.14
- **JLS §15.23–§15.24 — Conditional-And / Conditional-Or Operators**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.23
- **JLS §15.26 — Assignment Operators**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26
- **JLS §14 — Blocks, Statements, and Patterns (for, while, break, continue)**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html
- **JVMS SE 17, §2.6 — Frames; §2.11 — Instruction Set Summary**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html
- **JVMS SE 17, §6.5 — Instructions (iload, istore, iinc, branch, invoke, dup, array/field)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html

**Remember:** to predict execution order, read bytecode as **a state flow** consisting of **PC + locals + operand stack + side effects + branches**, rather than reading it as a list of instructions executed sequentially exactly once. Java guarantees observable evaluation order; javac implements it with load/store instructions, operations, jumps, and stack manipulation. When encountering **++**, **+=**, **&&**, loops, and array assignments, always track **old value, new value, evaluation count, and jump paths**. Missing any of these factors makes it very easy to deduce the wrong output even when you recognize every opcode correctly.
